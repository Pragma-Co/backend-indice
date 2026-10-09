import hashlib
import hmac

from django.conf import settings

from core.models.excluded_identifier import ExcludedIdentifier


class ExcludedIdentifierError(ValueError):
    """Raised when an excluded identifier is submitted for account use."""


def normalize_identifier(identifier):
    return identifier.strip().casefold()


def _identifier_hash(identifier):
    key = settings.EXCLUDED_IDENTIFIER_HMAC_KEY.encode("utf-8")
    message = b"excluded-identifier:v1:" + normalize_identifier(identifier).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def store_excluded_identifier(identifier):
    identifier_hash = _identifier_hash(identifier)
    excluded, _ = ExcludedIdentifier.objects.get_or_create(identifier_hash=identifier_hash)
    return excluded


def is_identifier_excluded(identifier):
    return ExcludedIdentifier.objects.filter(identifier_hash=_identifier_hash(identifier)).exists()


def ensure_identifier_is_available(identifier):
    if is_identifier_excluded(identifier):
        raise ExcludedIdentifierError("This email address cannot be used for an account.")
