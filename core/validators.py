from dataclasses import dataclass


@dataclass(frozen=True)
class AllowedFileType:
    mime_type: str
    extension: str
    signature: bytes
    offset: int = 0


ALLOWED_FILE_TYPES = [
    AllowedFileType(mime_type="application/pdf", extension="pdf", signature=b"%PDF-"),
    AllowedFileType(
        mime_type="application/msword",
        extension="doc",
        signature=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    ),
    AllowedFileType(mime_type="image/jpeg", extension="jpg", signature=b"\xff\xd8\xff"),
    AllowedFileType(
        mime_type="image/png", extension="png", signature=b"\x89PNG\r\n\x1a\n"
    ),
]

_MAX_SIGNATURE_LENGTH = max(t.offset + len(t.signature) for t in ALLOWED_FILE_TYPES)


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


def format_file_size(size_in_bytes: int) -> str:
    size = float(size_in_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"