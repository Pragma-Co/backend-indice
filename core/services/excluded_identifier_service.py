import hashlib
import hmac

from django.conf import settings

from core.models.excluded_identifier import ExcludedIdentifier


class ExcludedIdentifierError(ValueError):
    pass


def normalize_identifier(identifier):
    return identifier.strip().casefold()


def hash_identifier(identifier):
    key = settings.EXCLUDED_IDENTIFIER_HMAC_KEY.encode("utf-8")
    message = b"excluded-identifier:v1:" + normalize_identifier(identifier).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def store_excluded_identifier(identifier):
    identifier_hash = hash_identifier(identifier)
    excluded, _ = ExcludedIdentifier.objects.get_or_create(identifier_hash=identifier_hash)
    return excluded


def is_identifier_excluded(identifier):
    return ExcludedIdentifier.objects.filter(identifier_hash=hash_identifier(identifier)).exists()


def excluded_identifier_hashes():
    return set(ExcludedIdentifier.objects.values_list("identifier_hash", flat=True))


def ensure_identifier_is_available(identifier):
    if is_identifier_excluded(identifier):
        raise ExcludedIdentifierError("This email address cannot be used for an account.")
