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