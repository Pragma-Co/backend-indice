"""Errors raised by the document creation service, mapped to HTTP by the view."""


class DocumentValidationError(Exception):
    """The payload is incomplete or inconsistent. ``errors`` maps field -> message."""

    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid document payload: {sorted(errors)}")


class TempFileNotFoundError(Exception):
    """No file in temporary storage matches the given temp_file_id."""


class DuplicateDocumentFileError(Exception):
    """The uploaded file is already attached to a registered document."""

    def __init__(self, existing_file):
        self.existing_file = existing_file
        self.document = existing_file.revision.document
        super().__init__(f"File already registered under document {self.document.code}")


class DocumentStorageError(Exception):
    """The file could not be moved to the definitive storage."""


class DocumentCodeCollisionError(Exception):
    """A unique code could not be obtained after the configured number of retries."""
