class MissingFileError(Exception):
    pass


class FileTooLargeError(Exception):
    def __init__(self, max_size_bytes):
        self.max_size_bytes = max_size_bytes
        super().__init__("File exceeds the maximum allowed size")


class InvalidFileTypeError(Exception):
    pass


class UploadStorageError(Exception):
    pass


class DuplicateFileError(Exception):
    def __init__(self, existing_file):
        revision = existing_file.revision
        document = revision.document

        self.existing_file = existing_file
        self.document_id = document.id
        self.codigo_ra = document.code
        self.titulo = document.title
        self.status = revision.status
        self.data_upload = existing_file.uploaded_at

        super().__init__(f"Arquivo duplicado detectado: já existe no documento {document.code}")
