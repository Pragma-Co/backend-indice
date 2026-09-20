import logging
import uuid
from pathlib import Path

from django.conf import settings

from core.models import File
from core.mongo import get_mongo_db
from core.services.document_text_service import extract_text_for_ai
from core.services.file_validation_service import (
    calculate_file_hash,
    format_file_size,
    validate_file_size,
    validate_file_type,
)
from core.services.upload_exceptions import DuplicateFileError, MissingFileError, UploadStorageError

logger = logging.getLogger(__name__)


def store_uploaded_file(uploaded_file):
    if uploaded_file is None:
        raise MissingFileError()

    validate_file_size(uploaded_file)
    file_type = validate_file_type(uploaded_file)

    file_hash = calculate_file_hash(uploaded_file)

    existing_file = (
        File.objects.filter(sha256=file_hash)
        .select_related("revision__document")
        .order_by("-uploaded_at")
        .first()
    )
    if existing_file is not None:
        raise DuplicateFileError(existing_file)

    temp_file_id = str(uuid.uuid4())
    temp_dir = Path(settings.TEMP_UPLOAD_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    stored_path = temp_dir / f"{temp_file_id}.{file_type.extension}"

    try:
        with open(stored_path, "wb") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
    except OSError as exc:
        logger.exception("Failed to persist uploaded file to temp storage")
        raise UploadStorageError() from exc

    extracted_text = extract_text_for_ai(stored_path, file_type.extension)

    metadata = {
        "temp_file_id": temp_file_id,
        "original_name": uploaded_file.name,
        "stored_path": str(stored_path),
        "file_size_bytes": uploaded_file.size,
        "inferred_type": file_type.mime_type,
        "extension": file_type.extension,
        "sha256": file_hash,
        "extracted_text": extracted_text,
    }

    try:
        get_mongo_db()["temp_uploads"].insert_one(dict(metadata))
    except Exception:
        logger.exception("Failed to persist temp upload metadata to MongoDB")

    return {
        "temp_file_id": temp_file_id,
        "original_name": uploaded_file.name,
        "file_size": format_file_size(uploaded_file.size),
        "inferred_type": file_type.mime_type,
        "sha256": file_hash,
    }


def get_temp_upload_record(temp_file_id: str) -> dict:
    try:
        record = get_mongo_db()["temp_uploads"].find_one({"temp_file_id": temp_file_id})
    except Exception:
        logger.exception("Could not read temp upload metadata from MongoDB")
        return {}
    return record if isinstance(record, dict) else {}
