class AccessRequestValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid access request review payload: {sorted(errors)}")


class AccessRequestNotFoundError(Exception):
    pass


class AccessRequestAlreadyDecidedError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Access request was already decided with status {status}")


class OwnAccessRequestReviewError(Exception):
    pass
