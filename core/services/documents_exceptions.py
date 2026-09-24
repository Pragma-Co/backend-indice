class DocumentNotFoundError(Exception):
    pass


class MissingUserError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class AccessDeniedError(Exception):
    pass


class AlreadyHasAccessError(Exception):
    pass


class DocumentFileNotFoundError(Exception):
    pass
