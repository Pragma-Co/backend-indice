import hashlib
import logging
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import (
    Area,
    ConfidentialityLevel,
    Discipline,
    Document,
    DocumentArea,
    DocumentType,
    File,
    FileExtension,
    Project,
    Revision,
    RevisionStatus,
    User,
)
from core.models.upload_file_type import ALLOWED_FILE_TYPES
from core.mongo import get_mongo_db
from core.services.document_code_service import (
    build_code_prefix,
    build_document_code,
    next_sequence,
)
from core.services.document_exceptions import (
    DocumentCodeCollisionError,
    DocumentStorageError,
    DocumentValidationError,
    DuplicateDocumentFileError,
    TempFileNotFoundError,
)
from core.services.documents_exceptions import DocumentNotFoundError

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = Document._meta.get_field("title").max_length
DESCRIPTION_MAX_LENGTH = Document._meta.get_field("description").max_length
INITIAL_VERSION = 1
CODE_GENERATION_ATTEMPTS = 5
MIME_TYPE_BY_EXTENSION = {
    file_type.extension: file_type.mime_type for file_type in ALLOWED_FILE_TYPES
}
DEFAULT_MIME_TYPE = "application/octet-stream"
HASH_CHUNK_SIZE = 64 * 1024


REQUIRED = "required"
INVALID = "invalid"
TOO_LONG = "too_long"
NOT_FOUND = "not_found"
NOT_IN_PROJECT = "not_in_project"
INVALID_CHOICE = "invalid_choice"


def _error(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def _clean_text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _clean_code_list(value) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    codes = []
    for item in value:
        code = item.strip().upper()
        if code and code not in codes:
            codes.append(code)
    return codes


def validate_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise DocumentValidationError({"payload": _error(INVALID, "A JSON object is required.")})

    errors = {}
    cleaned = {}

    title = _clean_text(payload.get("title"))
    if not title:
        errors["title"] = _error(REQUIRED, "Title is required.")
    elif len(title) > TITLE_MAX_LENGTH:
        errors["title"] = _error(
            TOO_LONG, f"Title must have at most {TITLE_MAX_LENGTH} characters."
        )
    cleaned["title"] = title

    description = _clean_text(payload.get("description"))
    if len(description) > DESCRIPTION_MAX_LENGTH:
        errors["description"] = _error(
            TOO_LONG, f"Description must have at most {DESCRIPTION_MAX_LENGTH} characters."
        )
    cleaned["description"] = description

    project = None
    project_id = _clean_id(payload.get("project_id"))
    if project_id is None:
        errors["project_id"] = _error(REQUIRED, "Project is required.")
    else:
        project = Project.objects.filter(pk=project_id, active=True).first()
        if project is None:
            errors["project_id"] = _error(NOT_FOUND, "Project not found or inactive.")
    cleaned["project"] = project

    discipline = None
    discipline_id = _clean_id(payload.get("discipline_id"))
    if discipline_id is None:
        errors["discipline_id"] = _error(REQUIRED, "Discipline is required.")
    else:
        discipline = Discipline.objects.filter(pk=discipline_id, active=True).first()
        if discipline is None:
            errors["discipline_id"] = _error(NOT_FOUND, "Discipline not found or inactive.")
        elif project is not None and not project.disciplines.filter(pk=discipline.pk).exists():
            errors["discipline_id"] = _error(
                NOT_IN_PROJECT, "Discipline is not part of the selected project."
            )
    cleaned["discipline"] = discipline

    document_type = None
    type_id = _clean_id(payload.get("document_type"))
    print(f"Validating document type: {type_id}\n\n{payload.get('document_type')}")
    if not type_id:
        errors["document_type"] = _error(REQUIRED, "Document type is required.")
    else:
        document_type = DocumentType.objects.filter(id=type_id, active=True).first()
        if document_type is None:
            errors["document_type"] = _error(NOT_FOUND, "Document type not found or inactive.")
    cleaned["document_type"] = document_type

    confidentiality = _clean_text(payload.get("confidentiality")).upper()
    if not confidentiality:
        errors["confidentiality"] = _error(REQUIRED, "Confidentiality level is required.")
    elif confidentiality not in ConfidentialityLevel.values:
        errors["confidentiality"] = _error(
            INVALID_CHOICE,
            f"Confidentiality level must be one of {ConfidentialityLevel.values}.",
        )
    cleaned["confidentiality"] = confidentiality

    responsible = None
    responsible_id = _clean_id(payload.get("responsible_id"))
    if responsible_id is None:
        errors["responsible_id"] = _error(REQUIRED, "Responsible is required.")
    else:
        responsible = User.objects.filter(pk=responsible_id, is_active=True).first()
        if responsible is None:
            errors["responsible_id"] = _error(NOT_FOUND, "Responsible user not found or inactive.")
    cleaned["responsible"] = responsible

    created_by = None
    created_by_id = _clean_id(payload.get("user_id")) or _clean_id(payload.get("created_by_id"))
    if created_by_id is not None:
        created_by = User.objects.filter(pk=created_by_id, is_active=True).first()
        if created_by is None:
            errors["user_id"] = _error(NOT_FOUND, "User not found or inactive.")
    if created_by is None:
        created_by = responsible
    cleaned["created_by"] = created_by

    areas = []
    area_codes = _clean_code_list(payload.get("areas"))
    if area_codes is None:
        errors["areas"] = _error(INVALID, "Areas must be a list of area acronyms.")
    elif not area_codes:
        errors["areas"] = _error(REQUIRED, "At least one area is required.")
    else:
        areas = list(Area.objects.filter(acronym__in=area_codes, active=True))
        missing = sorted(set(area_codes) - {area.acronym for area in areas})
        if missing:
            errors["areas"] = _error(NOT_FOUND, f"Unknown or inactive areas: {missing}.")
    cleaned["areas"] = areas

    has_temp_file_ids = "temp_file_ids" in payload
    raw_temp_file_ids = payload.get("temp_file_ids")
    if raw_temp_file_ids is None:
        raw_temp_file_ids = [payload.get("temp_file_id")]
    if not isinstance(raw_temp_file_ids, list) or not raw_temp_file_ids:
        error_field = "temp_file_ids" if has_temp_file_ids else "temp_file_id"
        errors[error_field] = _error(REQUIRED, "At least one temporary file is required.")
        temp_file_ids = []
    else:
        temp_file_ids = [_clean_text(value) for value in raw_temp_file_ids]
        if not any(temp_file_ids):
            error_field = "temp_file_ids" if has_temp_file_ids else "temp_file_id"
            errors[error_field] = _error(REQUIRED, "At least one temporary file is required.")
        else:
            invalid_ids = []
            for temp_file_id in temp_file_ids:
                try:
                    uuid.UUID(temp_file_id)
                except (ValueError, AttributeError):
                    invalid_ids.append(temp_file_id)
            if invalid_ids:
                error_field = "temp_file_ids" if has_temp_file_ids else "temp_file_id"
                errors[error_field] = _error(INVALID, "Every temporary file id must be a UUID.")
    cleaned["temp_file_ids"] = temp_file_ids
    cleaned["temp_file_id"] = temp_file_ids[0] if temp_file_ids else None

    if errors:
        raise DocumentValidationError(errors)
    return cleaned


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temp_upload_record(temp_file_id: str) -> dict:
    try:
        record = get_mongo_db()["temp_uploads"].find_one({"temp_file_id": temp_file_id})
    except Exception:
        logger.exception("Could not read temp upload metadata from MongoDB")
        return {}
    return record if isinstance(record, dict) else {}


def resolve_temp_file(temp_file_id: str) -> dict:
    temp_dir = Path(settings.TEMP_UPLOAD_DIR)
    matches = sorted(temp_dir.glob(f"{temp_file_id}.*")) if temp_dir.is_dir() else []
    if not matches:
        raise TempFileNotFoundError(temp_file_id)

    path = matches[0]
    extension = path.suffix.lstrip(".").lower()
    if extension not in FileExtension.values:
        raise TempFileNotFoundError(temp_file_id)

    record = _temp_upload_record(temp_file_id)
    original_name = record.get("original_name")
    mime_type = record.get("inferred_type")
    return {
        "path": path,
        "extension": extension,
        "original_name": (
            original_name if isinstance(original_name, str) and original_name else path.name
        ),
        "mime_type": mime_type
        if isinstance(mime_type, str) and mime_type
        else MIME_TYPE_BY_EXTENSION.get(extension, DEFAULT_MIME_TYPE),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_of(path),
    }


def _discard_temp_record(temp_file_id: str) -> None:
    try:
        get_mongo_db()["temp_uploads"].delete_one({"temp_file_id": temp_file_id})
    except Exception:
        logger.exception("Could not remove temp upload metadata from MongoDB")


def _create_document_with_unique_code(cleaned: dict) -> Document:
    prefix = build_code_prefix(cleaned["project"], cleaned["discipline"], cleaned["document_type"])
    for _attempt in range(CODE_GENERATION_ATTEMPTS):
        code = build_document_code(prefix, next_sequence(prefix))
        try:
            with transaction.atomic():
                return Document.objects.create(
                    code=code,
                    title=cleaned["title"],
                    description=cleaned["description"],
                    project=cleaned["project"],
                    discipline=cleaned["discipline"],
                    document_type=cleaned["document_type"],
                    confidentiality_level=cleaned["confidentiality"],
                    responsible=cleaned["responsible"],
                    created_by=cleaned["created_by"],
                    updated_by=cleaned["created_by"],
                )
        except IntegrityError as exc:
            if "document_code" not in str(exc):
                raise
            logger.warning("Document code %s already taken, retrying", code)
    raise DocumentCodeCollisionError(prefix)


def storage_path_for(code: str, version: int, extension: str, file_index: int = 0) -> str:
    suffix = "" if file_index == 0 else f"-{file_index + 1}"
    return f"documents/{code}/v{version}/{code.lower()}{suffix}.{extension}"


def _move_to_storage(temp_path: Path, storage_path: str) -> None:
    destination = Path(settings.DOCUMENT_STORAGE_DIR) / storage_path
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_path), str(destination))
    except OSError as exc:
        logger.exception("Failed to move %s to definitive storage", temp_path.name)
        raise DocumentStorageError() from exc


def create_document(payload) -> Document:
    cleaned = validate_payload(payload)
    temp_files = []
    for temp_file_id in cleaned["temp_file_ids"]:
        temp_file = resolve_temp_file(temp_file_id)
        temp_file["temp_file_id"] = temp_file_id
        temp_files.append(temp_file)

        existing_file = (
            File.objects.filter(sha256=temp_file["sha256"])
            .select_related("revision__document")
            .order_by("-uploaded_at")
            .first()
        )
        if existing_file is not None:
            raise DuplicateDocumentFileError(existing_file)

    with transaction.atomic():
        document = _create_document_with_unique_code(cleaned)
        DocumentArea.objects.bulk_create(
            [DocumentArea(document=document, area=area) for area in cleaned["areas"]]
        )
        revision = Revision.objects.create(
            document=document,
            version=INITIAL_VERSION,
            status=RevisionStatus.PENDING,
            issue_date=timezone.localdate(),
            author=cleaned["responsible"],
        )
        for file_index, temp_file in enumerate(temp_files):
            storage_path = storage_path_for(
                document.code, revision.version, temp_file["extension"], file_index
            )
            File.objects.create(
                revision=revision,
                original_name=temp_file["original_name"][:255],
                extension=temp_file["extension"],
                mime_type=temp_file["mime_type"][:127],
                size_bytes=temp_file["size_bytes"],
                sha256=temp_file["sha256"],
                storage_path=storage_path,
            )
            _move_to_storage(temp_file["path"], storage_path)

    for temp_file_id in cleaned["temp_file_ids"]:
        _discard_temp_record(temp_file_id)
    return document


def create_document_revision(document_id, temp_file_id, source_file_id) -> Revision:
    document = (
        Document.objects.select_related("responsible")
        .filter(pk=document_id, document_type__active=True)
        .first()
    )
    if document is None:
        raise DocumentNotFoundError()

    source_file = (
        File.objects.filter(pk=source_file_id, revision__document=document)
        .select_related("revision")
        .first()
    )
    if source_file is None:
        raise DocumentNotFoundError()

    temp_file = resolve_temp_file(temp_file_id)
    existing_file = (
        File.objects.filter(sha256=temp_file["sha256"])
        .select_related("revision__document")
        .order_by("-uploaded_at")
        .first()
    )
    if existing_file is not None:
        raise DuplicateDocumentFileError(existing_file)

    last_version = (
        Revision.objects.filter(document=document)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    )
    revision = None
    current_revision = (
        Revision.objects.filter(document=document)
        .order_by("-version")
        .prefetch_related("files")
        .first()
    )
    if current_revision is None:
        raise DocumentNotFoundError()

    with transaction.atomic():
        revision = Revision.objects.create(
            document=document,
            version=last_version + 1,
            status=RevisionStatus.PENDING,
            issue_date=timezone.localdate(),
            author=document.responsible,
        )
        for file_index, current_file in enumerate(current_revision.files.all()):
            if current_file.pk == source_file.pk:
                file_info = temp_file
                source_path = None
            else:
                source_path = Path(settings.DOCUMENT_STORAGE_DIR) / current_file.storage_path
                if not source_path.exists():
                    raise DocumentStorageError()
                file_info = {
                    "original_name": current_file.original_name,
                    "extension": current_file.extension,
                    "mime_type": current_file.mime_type,
                    "size_bytes": current_file.size_bytes,
                    "sha256": current_file.sha256,
                }
            storage_path = storage_path_for(
                document.code, revision.version, file_info["extension"], file_index
            )
            File.objects.create(
                revision=revision,
                original_name=file_info["original_name"][:255],
                extension=file_info["extension"],
                mime_type=file_info["mime_type"][:127],
                size_bytes=file_info["size_bytes"],
                sha256=file_info["sha256"],
                file_group=current_file.file_group,
                revision_changed=current_file.pk == source_file.pk,
                storage_path=storage_path,
            )
            if source_path is None:
                _move_to_storage(temp_file["path"], storage_path)
            else:
                destination = Path(settings.DOCUMENT_STORAGE_DIR) / storage_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination)

    _discard_temp_record(temp_file_id)
    return revision
