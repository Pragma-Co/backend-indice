import functools
import ipaddress
import logging

from django.conf import settings
from django.db import transaction

from core.models import AuditAction, AuditLog, User
from core.services.document_code_service import revision_label

logger = logging.getLogger(__name__)

ENTITY_DOCUMENT = "document"
ENTITY_TEMP_UPLOAD = "temp_upload"

STAGE_UPLOAD = "upload"
STAGE_SUBMIT = "submit"

USER_AGENT_MAX_LENGTH = 512


def never_raises(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            logger.exception("Audit log write failed in %s", function.__name__)
            return None

    return wrapper


def client_ip(request):
    candidates = []
    if getattr(settings, "AUDIT_TRUST_FORWARDED_FOR", False):
        candidates.append(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0])
    candidates.append(request.META.get("REMOTE_ADDR", ""))
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate.strip()))
        except ValueError:
            continue
    return None


def client_user_agent(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:USER_AGENT_MAX_LENGTH]


def _declared_user_id(request, body):
    candidates = [request.POST.get("user_id"), request.GET.get("user_id")]
    if isinstance(body, dict):
        candidates.insert(0, body.get("user_id"))
    for value in candidates:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _resolve_actor(request, body):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user, True
    declared_user_id = _declared_user_id(request, body)
    if declared_user_id is None:
        return None, False
    return User.objects.filter(pk=declared_user_id, is_active=True).first(), False


@never_raises
def log_event(request, action, entity, entity_id=None, details=None, body=None):
    with transaction.atomic():
        actor, authenticated = _resolve_actor(request, body)
        record = dict(details or {})
        if actor is not None:
            record["actor"] = {
                "id": actor.pk,
                "name": actor.name,
                "authenticated": authenticated,
            }
        AuditLog.objects.create(
            user=actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            record=record,
            ip_address=client_ip(request),
        )


@never_raises
def log_temp_upload(request, result):
    if result.get("revision_created"):
        document = result["document"]
        log_event(
            request,
            AuditAction.DOC_UPLOAD_SUCCESS,
            ENTITY_DOCUMENT,
            document["id"],
            {
                "revision_created": True,
                "version": document["version"],
                "sha256": result["sha256"],
            },
        )
        return
    log_event(
        request,
        AuditAction.DOC_UPLOAD_SUCCESS,
        ENTITY_TEMP_UPLOAD,
        None,
        {
            "temp_file_id": result["temp_file_id"],
            "original_name": result["original_name"],
            "sha256": result["sha256"],
        },
    )


@never_raises
def log_duplicate_attempt(request, existing_file, stage, details=None, body=None):
    document = existing_file.revision.document
    log_event(
        request,
        AuditAction.DOC_UPLOAD_DUPLICATE,
        ENTITY_DOCUMENT,
        document.id,
        {
            "stage": stage,
            "document_code": document.code,
            "sha256": existing_file.sha256,
            **(details or {}),
        },
        body,
    )


@never_raises
def log_document_submitted(request, document, body, revision=None):
    if revision is None:
        revision = document.revisions.order_by("-version").first()
    version = getattr(revision, "version", None)
    log_event(
        request,
        AuditAction.DOC_SUBMIT_SUCCESS,
        ENTITY_DOCUMENT,
        document.id,
        {
            "document_code": document.code,
            "temp_file_id": body.get("temp_file_id"),
            "title": document.title,
            "version": version,
            "revision": revision_label(version) if version is not None else None,
            "user_agent": client_user_agent(request),
            "responsible_id": document.responsible_id,
        },
        body,
    )