import ipaddress
import logging

from django.db import transaction

from core.models import AuditAction, AuditLog, Document
from core.services.document_code_service import revision_label

logger = logging.getLogger(__name__)

DOCUMENT_ENTITY = "document"
DOCUMENT_CREATED_EVENT = "DOCUMENT_CREATED"
DOCUMENT_ACCESS_DENIED_EVENT = "DOCUMENT_ACCESS_DENIED"
USER_AGENT_MAX_LENGTH = 512


def _valid_ip(value) -> str | None:
    candidate = (value or "").strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip(request) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    first_hop = forwarded_for.split(",")[0]
    return _valid_ip(first_hop) or _valid_ip(request.META.get("REMOTE_ADDR"))


def client_user_agent(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:USER_AGENT_MAX_LENGTH]


def record_document_created(document: Document, request) -> AuditLog | None:
    try:
        revision = document.revisions.order_by("version").first()
        version = revision.version if revision is not None else None
        with transaction.atomic():
            return AuditLog.objects.create(
                user=document.responsible,
                action=AuditAction.CREATE,
                entity=DOCUMENT_ENTITY,
                entity_id=document.id,
                record={
                    "event": DOCUMENT_CREATED_EVENT,
                    "code": document.code,
                    "title": document.title,
                    "version": version,
                    "revision": revision_label(version) if version is not None else None,
                    "user_agent": client_user_agent(request),
                },
                ip_address=client_ip(request),
            )
    except Exception:
        logger.exception("Failed to record the %s audit event", DOCUMENT_CREATED_EVENT)
        return None


def record_document_access_denied(document: Document, user, request) -> AuditLog | None:
    try:
        with transaction.atomic():
            return AuditLog.objects.create(
                user=user,
                action=AuditAction.READ,
                entity=DOCUMENT_ENTITY,
                entity_id=document.id,
                record={
                    "event": DOCUMENT_ACCESS_DENIED_EVENT,
                    "code": document.code,
                    "outcome": "denied",
                    "user_agent": client_user_agent(request),
                },
                ip_address=client_ip(request),
            )
    except Exception:
        logger.exception("Failed to record the %s audit event", DOCUMENT_ACCESS_DENIED_EVENT)
        return None
