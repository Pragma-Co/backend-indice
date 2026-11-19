import gzip
import hashlib
import io
import json
import logging
import secrets
from datetime import UTC
from pathlib import Path

from bson import json_util
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.management import call_command
from django.core.paginator import Paginator
from django.utils import timezone

from core.models import BackupRun
from core.models.choices import BackupStatus, BackupTarget
from core.mongo import get_mongo_db

logger = logging.getLogger(__name__)

FILE_MAGIC = b"api6-backup-v1\n"
NONCE_SIZE = 12
KEY_SIZE = 32
FILE_SUFFIX = ".json.gz.enc"
EXCLUDED_POSTGRES_MODELS = ("contenttypes", "auth.permission", "admin.logentry", "sessions")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class BackupConfigurationError(Exception):
    pass


class BackupFileError(Exception):
    pass


class BackupQueryError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__(f"Invalid backup query: {sorted(errors)}")


def encryption_key() -> bytes:
    try:
        key = bytes.fromhex(settings.BACKUP_ENCRYPTION_KEY or "")
    except ValueError as exc:
        raise BackupConfigurationError("BACKUP_ENCRYPTION_KEY must be hexadecimal.") from exc
    if len(key) != KEY_SIZE:
        raise BackupConfigurationError("BACKUP_ENCRYPTION_KEY must have 64 hex characters.")
    return key


def encrypt(data: bytes, key: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_SIZE)
    return FILE_MAGIC + nonce + AESGCM(key).encrypt(nonce, data, FILE_MAGIC)


def decrypt(blob: bytes, key: bytes) -> bytes:
    if not blob.startswith(FILE_MAGIC):
        raise BackupFileError("Not an api6 backup file.")
    start = len(FILE_MAGIC)
    nonce = blob[start : start + NONCE_SIZE]
    return AESGCM(key).decrypt(nonce, blob[start + NONCE_SIZE :], FILE_MAGIC)


def export_postgres():
    buffer = io.StringIO()
    call_command("dumpdata", exclude=list(EXCLUDED_POSTGRES_MODELS), format="json", stdout=buffer)
    payload = buffer.getvalue()
    return payload.encode("utf-8"), len(json.loads(payload))


def export_mongodb():
    database = get_mongo_db()
    collections = {}
    count = 0
    for name in sorted(database.list_collection_names()):
        documents = list(database[name].find())
        collections[name] = documents
        count += len(documents)
    payload = json_util.dumps({"database": database.name, "collections": collections})
    return payload.encode("utf-8"), count


EXPORTERS = {
    BackupTarget.POSTGRES: export_postgres,
    BackupTarget.MONGODB: export_mongodb,
}


def retention_limit(target) -> int:
    if target == BackupTarget.POSTGRES:
        return settings.BACKUP_KEEP_POSTGRES
    return settings.BACKUP_KEEP_MONGODB


def snapshot_path(target, moment, run_id) -> Path:
    stamp = moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"{target.lower()}-{stamp}-{run_id}{FILE_SUFFIX}"
    return Path(settings.BACKUP_DIR) / target.lower() / name


def run_backup(target, triggered_by=None, keep=None) -> BackupRun:
    target = BackupTarget(target)
    run = BackupRun.objects.create(target=target, triggered_by=triggered_by)
    try:
        key = encryption_key()
        payload, record_count = EXPORTERS[target]()
        encrypted = encrypt(gzip.compress(payload), key)
        path = snapshot_path(target, timezone.now(), run.pk)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encrypted)
        run.destination = str(path)
        run.size_bytes = len(encrypted)
        run.sha256 = hashlib.sha256(encrypted).hexdigest()
        run.encrypted = True
        run.record_count = record_count
        run.status = BackupStatus.SUCCEEDED
    except Exception as exc:
        logger.exception("Backup of %s failed", target)
        run.status = BackupStatus.FAILED
        run.error = type(exc).__name__
    run.finished_at = timezone.now()
    run.save()
    if run.status == BackupStatus.SUCCEEDED:
        prune_snapshots(target, retention_limit(target) if keep is None else keep)
    return run


def prune_snapshots(target, keep):
    retained = BackupRun.objects.filter(
        target=target, status=BackupStatus.SUCCEEDED, pruned_at__isnull=True
    ).order_by("-started_at", "-id")
    for stale in list(retained[max(keep, 0) :]):
        path = Path(stale.destination)
        if path.exists():
            path.unlink()
        stale.pruned_at = timezone.now()
        stale.save(update_fields=["pruned_at"])


def decrypt_snapshot(source: Path, destination: Path) -> Path:
    plain = gzip.decompress(decrypt(source.read_bytes(), encryption_key()))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(plain)
    return destination


def _error(code, message):
    return {"code": code, "message": message}


def _positive_int(params, name, default, errors):
    raw = str(params.get(name, "") or "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        errors[name] = _error("invalid", f"{name} must be a positive integer.")
        return default
    return int(raw)


def list_backup_runs(params, serialize):
    errors = {}
    page_number = _positive_int(params, "page", 1, errors)
    page_size = min(_positive_int(params, "page_size", DEFAULT_PAGE_SIZE, errors), MAX_PAGE_SIZE)
    target = str(params.get("target", "") or "").strip().upper()
    if target and target not in BackupTarget.values:
        errors["target"] = _error(
            "invalid_choice", f"target must be one of {list(BackupTarget.values)}."
        )
    if errors:
        raise BackupQueryError(errors)
    queryset = BackupRun.objects.select_related("triggered_by")
    if target:
        queryset = queryset.filter(target=target)
    paginator = Paginator(queryset, page_size)
    items = paginator.page(page_number) if page_number <= paginator.num_pages else []
    return {
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_number,
        "page_size": page_size,
        "results": [serialize(run) for run in items],
    }
