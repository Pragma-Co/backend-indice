class IncidentValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid incident payload: {sorted(errors)}")


class IncidentQueryError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid incident query: {sorted(errors)}")


class IncidentNotFoundError(Exception):
    pass


class NoAffectedUsersError(Exception):
    pass


class IncidentClosedError(Exception):
    pass


class IncidentReferenceCollisionError(Exception):
    pass


class InvalidStatusTransitionError(Exception):
    def __init__(self, current, requested):
        self.current = current
        self.requested = requested
        super().__init__(f"Cannot move an incident from {current} to {requested}")


class IncidentClosureBlockedError(Exception):
    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__(f"Incident cannot be closed: {self.reasons}")
