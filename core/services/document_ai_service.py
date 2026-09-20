import logging
import re
import uuid
from pathlib import Path

from django.conf import settings

from core.groq_client import get_groq_client
from core.mongo import get_mongo_db
from core.services.catalog_service import (
    list_active_areas,
    list_active_disciplines,
    list_active_document_types,
    list_active_projects,
)
from core.services.document_ai_exceptions import AISuggestionError, UnsupportedFileTypeError
from core.services.document_exceptions import TempFileNotFoundError
from core.services.temp_upload_service import get_temp_upload_record

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {"pdf", "docx"}

TITLE_PATTERN = re.compile(r"T[IÍ]TULO:\s*(.+)", re.IGNORECASE)
DESCRIPTION_PATTERN = re.compile(r"DESCRI[ÇC][AÃ]O:\s*(.+)", re.IGNORECASE | re.DOTALL)


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


def _match_catalog_name(suggested_name: str, catalog_items) -> dict:
    normalized = suggested_name.strip().lower()
    for item in catalog_items:
        if item.name.strip().lower() == normalized:
            return {"id": item.id, "name": item.name}
    return {"id": None, "name": suggested_name.strip()}


def _parse_title_and_description(answer: str) -> tuple[str, str]:
    title_match = TITLE_PATTERN.search(answer)
    description_match = DESCRIPTION_PATTERN.search(answer)
    title = title_match.group(1).strip() if title_match else ""
    description = description_match.group(1).strip() if description_match else answer.strip()
    return title, description


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
        )
    except Exception as exc:
        logger.exception("Groq request failed")
        raise AISuggestionError() from exc
    return (response.choices[0].message.content or "").strip()


def _suggest_title_and_description(llm_text: str) -> tuple[str, str]:
    answer = _ask_groq(
        "Você é um assistente que nomeia e resume documentos técnicos de engenharia em "
        "português.",
        f"Analise o texto a seguir:\n\n{llm_text}\n\nResponda em exatamente duas linhas, "
        "neste formato, sem texto adicional:\nTÍTULO: <um título curto e objetivo para o "
        "documento>\nDESCRIÇÃO: <uma breve descrição, em português, do conteúdo do "
        "documento>",
    )
    return _parse_title_and_description(answer)


def _suggest_project(llm_text: str, projects: list) -> dict:
    project_names = [project.name for project in projects]
    answer = _ask_groq(
        "Você é um especialista em projetos de engenharia. Responda apenas com o nome de "
        "um projeto, exatamente como está escrito na lista fornecida.",
        f"Analise o texto a seguir:\n\n{llm_text}\n\nCom base nesse texto, qual dos "
        f"projetos a seguir é o mais adequado: {project_names}? Responda apenas com o nome "
        "do projeto, sem texto adicional.",
    )
    return _match_catalog_name(answer, projects)


def _suggest_discipline(llm_text: str, disciplines: list) -> dict:
    discipline_names = [discipline.name for discipline in disciplines]
    answer = _ask_groq(
        "Você é um especialista em disciplinas de engenharia. Responda apenas com o nome "
        "de uma disciplina, exatamente como está escrita na lista fornecida.",
        f"Analise o texto a seguir:\n\n{llm_text}\n\nCom base nesse texto, qual das "
        f"disciplinas a seguir é a mais adequada: {discipline_names}? Responda apenas com "
        "o nome da disciplina, sem texto adicional.",
    )
    return _match_catalog_name(answer, disciplines)


def _suggest_document_type(llm_text: str, document_types: list) -> dict:
    document_type_names = [document_type.name for document_type in document_types]
    answer = _ask_groq(
        "Você é um especialista em gestão documental de engenharia. Responda apenas com o "
        "nome de um tipo de documento, exatamente como está escrito na lista fornecida.",
        f"Analise o texto a seguir:\n\n{llm_text}\n\nCom base nesse texto, qual dos tipos "
        f"de documento a seguir é o mais adequado: {document_type_names}? Responda apenas "
        "com o nome do tipo de documento, sem texto adicional.",
    )
    return _match_catalog_name(answer, document_types)


def _suggest_area(llm_text: str, areas: list) -> dict:
    area_names = [area.name for area in areas]
    answer = _ask_groq(
        "Você é um especialista em áreas de engenharia responsáveis por documentos "
        "técnicos. Responda apenas com o nome de uma área, exatamente como está escrita "
        "na lista fornecida.",
        f"Analise o texto a seguir:\n\n{llm_text}\n\nCom base nesse texto, qual das áreas "
        f"a seguir é a mais adequada para ser responsável por este documento: "
        f"{area_names}? Responda apenas com o nome da área, sem texto adicional.",
    )
    return _match_catalog_name(answer, areas)


def suggest_document_metadata(temp_file_id: str) -> dict:
    path = _locate_temp_file(temp_file_id)
    extension = path.suffix.lstrip(".").lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(extension)

    record = get_temp_upload_record(temp_file_id)
    llm_text = record.get("extracted_text") or ""

    projects = list(list_active_projects())
    document_types = list(list_active_document_types())
    areas = list(list_active_areas())

    title, description = _suggest_title_and_description(llm_text)
    project = _suggest_project(llm_text, projects)

    matched_project = next((p for p in projects if p.id == project["id"]), None)
    discipline_candidates = (
        list(matched_project.disciplines.all())
        if matched_project is not None
        else list(list_active_disciplines())
    )
    discipline = _suggest_discipline(llm_text, discipline_candidates)
    document_type = _suggest_document_type(llm_text, document_types)
    area = _suggest_area(llm_text, areas)

    suggestion = {
        "title": title,
        "description": description,
        "project": project,
        "discipline": discipline,
        "document_type": document_type,
        "area": area,
    }
    _save_suggestion_to_temp_upload(temp_file_id, suggestion)
    return suggestion
