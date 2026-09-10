from django.conf import settings

from core.models.upload_file_type import ALLOWED_FILE_TYPES
from core.services.upload_exceptions import FileTooLargeError, InvalidFileTypeError

_MAX_SIGNATURE_LENGTH = max(t.offset + len(t.signature) for t in ALLOWED_FILE_TYPES)


def validate_file_size(uploaded_file):
    if uploaded_file.size > settings.MAX_UPLOAD_SIZE_BYTES:
        raise FileTooLargeError(settings.MAX_UPLOAD_SIZE_BYTES)


def sniff_file_type(uploaded_file):
    uploaded_file.seek(0)
    header = uploaded_file.read(_MAX_SIGNATURE_LENGTH)
    uploaded_file.seek(0)

    for file_type in ALLOWED_FILE_TYPES:
        start = file_type.offset
        end = start + len(file_type.signature)
        if header[start:end] == file_type.signature:
            return file_type
    return None


def validate_file_type(uploaded_file):
    file_type = sniff_file_type(uploaded_file)
    if file_type is None:
        raise InvalidFileTypeError()
    return file_type


def format_file_size(size_in_bytes: int) -> str:
    size = float(size_in_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"

