import logging
import uuid
from pathlib import Path

from django.conf import settings

from core.mongo import get_mongo_db
from core.services.file_validation_service import (
    format_file_size,
    validate_file_size,
    validate_file_type,
)
from core.services.upload_exceptions import MissingFileError, UploadStorageError

logger = logging.getLogger(__name__)


def store_uploaded_file(uploaded_file):
    if uploaded_file is None:
        raise MissingFileError()

    validate_file_size(uploaded_file)
    file_type = validate_file_type(uploaded_file)

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

    metadata = {
        "temp_file_id": temp_file_id,
        "original_name": uploaded_file.name,
        "stored_path": str(stored_path),
        "file_size_bytes": uploaded_file.size,
        "inferred_type": file_type.mime_type,
        "extension": file_type.extension,
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
    }