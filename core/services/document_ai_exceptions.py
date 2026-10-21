class UnsupportedFileTypeError(Exception):
    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(f"Unsupported file type for AI suggestions: {extension}")


class AISuggestionError(Exception):
    pass
