class RevisionReviewValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid revision review payload: {sorted(errors)}")


class RevisionNotFoundError(Exception):
    pass


class RevisionAlreadyDecidedError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Revision was already decided with status {status}")


class OwnRevisionReviewError(Exception):
    pass


class OutdatedRevisionError(Exception):
    def __init__(self, current_version):
        self.current_version = current_version
        super().__init__(f"Document already has the newer version {current_version} approved")
