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

