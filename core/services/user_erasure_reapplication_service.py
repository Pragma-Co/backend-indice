import gzip
import json
import logging
from pathlib import Path

from django.db import transaction

from core.models import AuditAction, AuditLog, ErasureKind, ExcludedIdentifier, User
from core.services.backup_service import BackupFileError, decrypt, encryption_key
from core.services.excluded_identifier_service import identifier_hash, register_excluded_hash
from core.services.user_anonymization_service import (
    NoReplacementManagerError,
    anonymize_user,
    delete_user_account,
    is_anonymized,
)

logger = logging.getLogger(__name__)

REGISTER_MODEL = "core.excludedidentifier"
ENTITY_USER = "app_user"
EVENT_ERASURE_REAPPLIED = "USER_ERASURE_REAPPLIED"


def load_register_from_snapshot(source: Path) -> int:
    payload = json.loads(gzip.decompress(decrypt(Path(source).read_bytes(), encryption_key())))
    if not isinstance(payload, list):
        raise BackupFileError("Not a PostgreSQL snapshot.")
    merged = 0
    with transaction.atomic():
        for item in payload:
            if item.get("model") != REGISTER_MODEL:
                continue
            fields = item["fields"]
            register_excluded_hash(
                fields["identifier_hash"], fields.get("kind", ErasureKind.ANONYMIZED)
            )
            merged += 1
    return merged


def _record_reapplied(user, kind):
    AuditLog.objects.create(
        user=None,
        action=AuditAction.DELETE,
        entity=ENTITY_USER,
        entity_id=user.pk,
        record={"event": EVENT_ERASURE_REAPPLIED, "kind": kind},
    )


def _reapply(user, kind):
    with transaction.atomic():
        if kind == ErasureKind.DELETED:
            delete_user_account(user)
        else:
            anonymize_user(user)
        _record_reapplied(user, kind)


def reapply_user_erasures():
    summary = {"anonymized": [], "deleted": [], "failed": []}
    register = dict(ExcludedIdentifier.objects.values_list("identifier_hash", "kind"))
    if not register:
        return summary
    for user_id in list(User.objects.order_by("pk").values_list("pk", flat=True)):
        user = User.objects.filter(pk=user_id).first()
        if user is None or is_anonymized(user):
            continue
        kind = register.get(identifier_hash(user.email))
        if kind is None:
            continue
        try:
            _reapply(user, kind)
        except NoReplacementManagerError:
            logger.warning("Erasure of user %s could not be re-applied: no replacement", user_id)
            summary["failed"].append(user_id)
            continue
        summary["deleted" if kind == ErasureKind.DELETED else "anonymized"].append(user_id)
    return summary
