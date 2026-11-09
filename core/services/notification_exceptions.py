class NotificationValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid notification query: {sorted(errors)}")


class NotificationNotFoundError(Exception):
    pass
