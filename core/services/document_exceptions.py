class DocumentValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid document payload: {sorted(errors)}")


class TempFileNotFoundError(Exception):
    pass


class DuplicateDocumentFileError(Exception):
    def __init__(self, existing_file):
        self.existing_file = existing_file
        self.document = existing_file.revision.document
        super().__init__(f"File already registered under document {self.document.code}")


class DocumentStorageError(Exception):
    pass


class DocumentCodeCollisionError(Exception):
    pass


class DocumentQueryError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid document query: {sorted(errors)}")
