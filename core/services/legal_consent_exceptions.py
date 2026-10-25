class LegalConsentValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid legal consent payload: {sorted(errors)}")


class LegalDocumentNotFoundError(Exception):
    pass


class LegalVersionNotFoundError(Exception):
    pass


class OutdatedLegalVersionError(Exception):
    def __init__(self, current_version_id):
        self.current_version_id = current_version_id
        super().__init__(f"Legal version superseded by version id {current_version_id}")


class LegalVersionAlreadyAcceptedError(Exception):
    pass


class LegalAcceptanceNotFoundError(Exception):
    pass


class LegalAcceptanceAlreadyRevokedError(Exception):
    pass
