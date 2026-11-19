import hashlib
import hmac

from django.conf import settings

from core.models.choices import ErasureKind
from core.models.excluded_identifier import ExcludedIdentifier


class ExcludedIdentifierError(ValueError):
    pass


def normalize_identifier(identifier):
    return identifier.strip().casefold()


def identifier_hash(identifier):
    key = settings.EXCLUDED_IDENTIFIER_HMAC_KEY.encode("utf-8")
    message = b"excluded-identifier:v1:" + normalize_identifier(identifier).encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def register_excluded_hash(hash_value, kind):
    excluded, created = ExcludedIdentifier.objects.get_or_create(
        identifier_hash=hash_value, defaults={"kind": kind}
    )
    if not created and kind == ErasureKind.DELETED and excluded.kind != kind:
        excluded.kind = kind
        excluded.save(update_fields=["kind"])
    return excluded


def store_excluded_identifier(identifier, kind):
    return register_excluded_hash(identifier_hash(identifier), kind)


def is_identifier_excluded(identifier):
    return ExcludedIdentifier.objects.filter(identifier_hash=identifier_hash(identifier)).exists()


def ensure_identifier_is_available(identifier):
    if is_identifier_excluded(identifier):
        raise ExcludedIdentifierError("This email address cannot be used for an account.")
