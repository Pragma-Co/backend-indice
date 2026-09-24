from dataclasses import dataclass


@dataclass(frozen=True)
class AllowedFileType:
    mime_type: str
    extension: str
    signature: bytes
    offset: int = 0


ALLOWED_FILE_TYPES = [
    AllowedFileType(mime_type="application/pdf", extension="pdf", signature=b"%PDF-"),
    AllowedFileType(mime_type="image/jpeg", extension="jpeg", signature=b"\xff\xd8\xff"),
    AllowedFileType(mime_type="image/png", extension="png", signature=b"\x89PNG\r\n\x1a\n"),
    AllowedFileType(
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        extension="docx",
        signature=b"PK\x03\x04",
    ),
]
