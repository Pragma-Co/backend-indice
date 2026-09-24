import json
import logging
import re
import uuid
from pathlib import Path

import groq
from django.conf import settings

from core.groq_client import get_groq_client
from core.mongo import get_mongo_db
from core.services.catalog_service import (
    list_active_areas,
    list_active_disciplines,
    list_active_document_types,
    list_active_projects,
)
from core.services.document_ai_exceptions import (
    AICommunicationError,
    AIRateLimitError,
    AISuggestionError,
    AITimeoutError,
    UnsupportedFileTypeError,
)
from core.services.document_exceptions import TempFileNotFoundError
from core.services.temp_upload_service import get_temp_upload_record

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {"pdf", "docx"}
SUGGESTION_FIELDS = ("title", "description", "project", "discipline", "document_type", "area")

SYSTEM_PROMPT = (
    "Você é um especialista em gestão documental de engenharia. Classifique documentos "
    "técnicos em português e responda sempre com um único objeto JSON válido, sem "
    "nenhum texto, comentário ou marcação adicional."
)

JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _locate_temp_file(temp_file_id: str) -> Path:
    try:
        uuid.UUID(temp_file_id)
    except ValueError as exc:
        raise TempFileNotFoundError(temp_file_id) from exc

    temp_dir = Path(settings.TEMP_UPLOAD_DIR)
    matches = sorted(temp_dir.glob(f"{temp_file_id}.*")) if temp_dir.is_dir() else []
    if not matches:
        raise TempFileNotFoundError(temp_file_id)
    return matches[0]


def _clean_text(value) -> str | None:
    return str(value or "").strip() or None


def _match_catalog_name(suggested_name, catalog_items) -> dict | None:
    name = _clean_text(suggested_name)
    if name is None:
        return None
    for item in catalog_items:
        if item.name.strip().lower() == name.lower():
            return {"id": item.id, "name": item.name}
    return {"id": None, "name": name}


def _save_suggestion_to_temp_upload(temp_file_id: str, suggestion: dict) -> None:
    try:
        get_mongo_db()["temp_uploads"].update_one(
            {"temp_file_id": temp_file_id},
            {"$set": {"ai_suggestion": suggestion}},
        )
    except Exception:
        logger.exception("Could not persist AI suggestion to MongoDB")


def _ask_groq(system_prompt: str, user_prompt: str) -> str:
    client = get_groq_client()
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=settings.GROQ_MODEL,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except groq.APITimeoutError as exc:
        logger.warning("Groq request timed out")
        raise AITimeoutError() from exc
    except groq.RateLimitError as exc:
        logger.warning("Groq rate limit exceeded")
        raise AIRateLimitError() from exc
    except groq.APIConnectionError as exc:
        logger.warning("Groq communication error: %s", exc)
        raise AICommunicationError() from exc
    except Exception as exc:
        logger.exception("Groq request failed")
        raise AISuggestionError() from exc
    return (response.choices[0].message.content or "").strip()


def _parse_json_answer(answer: str) -> dict:
    try:
        data = json.loads(answer)
    except (json.JSONDecodeError, TypeError) as exc:
        match = JSON_BLOCK_PATTERN.search(answer)
        if match is None:
            logger.error("Groq answer was not valid JSON: %r", answer)
            raise AISuggestionError() from exc
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            logger.error("Groq answer was not valid JSON: %r", answer)
            raise AISuggestionError() from exc

    if not isinstance(data, dict):
        raise AISuggestionError()
    return data


def _build_project_catalog_section(projects: list) -> str:
    lines = []
    for project in projects:
        discipline_names = ", ".join(discipline.name for discipline in project.disciplines.all())
        lines.append(f'- "{project.name}": disciplinas possíveis -> [{discipline_names}]')
    return "\n".join(lines)


def _build_user_prompt(llm_text: str, projects: list, document_types: list, areas: list) -> str:
    document_type_names = [document_type.name for document_type in document_types]
    area_names = [area.name for area in areas]

    return (
        "Analise o texto de um documento técnico de engenharia e responda apenas com um "
        'objeto JSON com exatamente estas chaves: "title" (título curto e objetivo, em '
        'português), "description" (breve descrição, em português, do conteúdo do '
        'documento), "project" (nome de um dos projetos listados abaixo), "discipline" '
        '(nome de uma das disciplinas possíveis do projeto escolhido), "document_type" '
        '(nome de um dos tipos de documento listados abaixo) e "area" (nome de uma das '
        "áreas listadas abaixo).\n\n"
        f"Projetos e suas disciplinas possíveis:\n{_build_project_catalog_section(projects)}\n\n"
        f"Tipos de documento possíveis: {document_type_names}\n\n"
        f"Áreas possíveis: {area_names}\n\n"
        f"Texto do documento:\n\n{llm_text}"
    )


def suggest_document_metadata(temp_file_id: str) -> dict:
    path = _locate_temp_file(temp_file_id)
    extension = path.suffix.lstrip(".").lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(extension)

    record = get_temp_upload_record(temp_file_id)
    llm_text = (record.get("extracted_text") or "").strip()
    if not llm_text:
        empty_suggestion = dict.fromkeys(SUGGESTION_FIELDS)
        _save_suggestion_to_temp_upload(temp_file_id, empty_suggestion)
        return empty_suggestion

    projects = list(list_active_projects())
    document_types = list(list_active_document_types())
    areas = list(list_active_areas())

    try:
        answer = _ask_groq(
            SYSTEM_PROMPT, _build_user_prompt(llm_text, projects, document_types, areas)
        )
        data = _parse_json_answer(answer)
    except AISuggestionError:
        data = {}

    project = _match_catalog_name(data.get("project"), projects)
    matched_project = (
        next((p for p in projects if p.id == project["id"]), None) if project else None
    )
    discipline_candidates = (
        list(matched_project.disciplines.all())
        if matched_project is not None
        else list(list_active_disciplines())
    )

    suggestion = {
        "title": _clean_text(data.get("title")),
        "description": _clean_text(data.get("description")),
        "project": project,
        "discipline": _match_catalog_name(data.get("discipline"), discipline_candidates),
        "document_type": _match_catalog_name(data.get("document_type"), document_types),
        "area": _match_catalog_name(data.get("area"), areas),
    }
    _save_suggestion_to_temp_upload(temp_file_id, suggestion)
    return suggestion
