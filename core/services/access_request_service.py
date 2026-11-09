from datetime import date

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import AccessStatus, AccessType, Area, Document, DocumentAccess
from core.services.access_request_exceptions import (
    AccessRequestAlreadyDecidedError,
    AccessRequestExpiredError,
    AccessRequestNotFoundError,
    AccessRequestValidationError,
    OwnAccessRequestReviewError,
)
from core.services.notification_service import notify_access_decided

DECISIONS = (AccessStatus.APPROVED, AccessStatus.REJECTED)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
JUSTIFICATION_MIN_LENGTH = 20
JUSTIFICATION_MAX_LENGTH = 1000


def _error(code, message):
    return {"code": code, "message": message}


def active_grant_filter() -> Q:
    return Q(status=AccessStatus.APPROVED) & (
        Q(expires_on__isnull=True) | Q(expires_on__gte=timezone.localdate())
    )


def _justification_error(justification):
    if justification is None or (isinstance(justification, str) and not justification.strip()):
        return _error("required", "Justification is required.")
    if not isinstance(justification, str):
        return _error("invalid", "justification must be a string.")
    length = len(justification.strip())
    if length < JUSTIFICATION_MIN_LENGTH:
        return _error(
            "too_short", f"justification must have at least {JUSTIFICATION_MIN_LENGTH} characters."
        )
    if length > JUSTIFICATION_MAX_LENGTH:
        return _error(
            "too_long", f"justification must have at most {JUSTIFICATION_MAX_LENGTH} characters."
        )
    return None


def _clean_access_type(raw_access_type, errors):
    if raw_access_type is None or (
        isinstance(raw_access_type, str) and not raw_access_type.strip()
    ):
        errors["access_type"] = _error("required", "access_type is required.")
        return None
    normalized = raw_access_type.strip().upper() if isinstance(raw_access_type, str) else None
    if normalized not in AccessType.values:
        errors["access_type"] = _error(
            "invalid_choice", f"access_type must be one of {AccessType.values}."
        )
        return None
    return AccessType(normalized)


def _clean_expires_on(raw_expires_on, access_type, errors):
    if access_type == AccessType.PERMANENT and raw_expires_on is not None:
        errors["expires_on"] = _error(
            "not_allowed", "expires_on is only accepted for TEMPORARY access."
        )
        return None
    if access_type != AccessType.TEMPORARY:
        return None
    if raw_expires_on is None or raw_expires_on == "":
        errors["expires_on"] = _error("required", "expires_on is required for TEMPORARY access.")
        return None
    try:
        expires_on = date.fromisoformat(raw_expires_on)
    except (TypeError, ValueError):
        errors["expires_on"] = _error("invalid", "expires_on must be a date in YYYY-MM-DD format.")
        return None
    if expires_on < timezone.localdate():
        errors["expires_on"] = _error("in_the_past", "expires_on cannot be in the past.")
        return None
    return expires_on


def validate_access_request_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise AccessRequestValidationError(
            {"body": _error("invalid", "Request body must be a JSON object.")}
        )

    errors = {}
    justification = payload.get("justification")
    justification_error = _justification_error(justification)
    if justification_error is not None:
        errors["justification"] = justification_error
    access_type = _clean_access_type(payload.get("access_type"), errors)
    expires_on = _clean_expires_on(payload.get("expires_on"), access_type, errors)
    if errors:
        raise AccessRequestValidationError(errors)
    return {
        "justification": justification.strip(),
        "access_type": access_type,
        "expires_on": expires_on,
    }


def decidable_documents(approver):
    return Document.objects.filter(document_type__active=True, archived_at__isnull=True).filter(
        Q(responsible=approver) | Q(areas__manager=approver, areas__active=True)
    )


def is_access_approver(user) -> bool:
    if not (user and user.is_authenticated and user.is_active):
        return False
    return (
        Area.objects.filter(manager=user, active=True).exists()
        or decidable_documents(user).exists()
    )


def _positive_int(params, name, default, errors):
    raw = (params.get(name) or "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        errors[name] = _error("invalid", f"{name} must be a positive integer.")
        return default
    return int(raw)


def parse_pending_query(params) -> dict:
    errors = {}
    page = _positive_int(params, "page", 1, errors)
    page_size = _positive_int(params, "page_size", DEFAULT_PAGE_SIZE, errors)
    if page_size > MAX_PAGE_SIZE:
        errors["page_size"] = _error("too_large", f"page_size must be at most {MAX_PAGE_SIZE}.")
    if errors:
        raise AccessRequestValidationError(errors)
    return {"page": page, "page_size": page_size}


def pending_access_requests(approver):
    return (
        DocumentAccess.objects.filter(
            status=AccessStatus.PENDING,
            document__in=decidable_documents(approver).values("pk"),
        )
        .exclude(user=approver)
        .select_related(
            "user__area",
            "document__project",
            "document__discipline",
            "document__document_type",
        )
        .order_by("requested_at", "id")
    )


def get_access_request_detail(access_id, approver) -> DocumentAccess:
    access = (
        DocumentAccess.objects.filter(
            pk=access_id,
            document__in=decidable_documents(approver).values("pk"),
        )
        .exclude(user=approver)
        .select_related(
            "user__area",
            "approver",
            "document__project",
            "document__discipline",
            "document__document_type",
            "document__responsible",
        )
        .prefetch_related("document__areas")
        .first()
    )
    if access is None:
        raise AccessRequestNotFoundError()
    return access


def list_pending_access_requests(approver, params) -> dict:
    query = parse_pending_query(params)
    paginator = Paginator(pending_access_requests(approver), query["page_size"])
    page_number = query["page"]
    items = paginator.page(page_number).object_list if page_number <= paginator.num_pages else []
    return {
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_number,
        "page_size": query["page_size"],
        "results": list(items),
    }


def validate_decision_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise AccessRequestValidationError(
            {"body": _error("invalid", "Request body must be a JSON object.")}
        )

    decision = payload.get("decision")
    if decision is None or (isinstance(decision, str) and not decision.strip()):
        raise AccessRequestValidationError(
            {"decision": _error("required", "Decision is required.")}
        )
    if not isinstance(decision, str) or decision.strip().upper() not in DECISIONS:
        raise AccessRequestValidationError(
            {
                "decision": _error(
                    "invalid_choice",
                    f"decision must be one of {[str(value) for value in DECISIONS]}.",
                )
            }
        )
    return {"decision": AccessStatus(decision.strip().upper())}


def decide_access_request(access_id, approver, payload) -> DocumentAccess:
    cleaned = validate_decision_payload(payload)

    with transaction.atomic():
        access = (
            DocumentAccess.objects.select_for_update(of=("self",))
            .select_related("document", "user")
            .filter(pk=access_id, document__in=decidable_documents(approver).values("pk"))
            .first()
        )
        if access is None:
            raise AccessRequestNotFoundError()
        if access.user_id == approver.pk:
            raise OwnAccessRequestReviewError()
        if access.status != AccessStatus.PENDING:
            raise AccessRequestAlreadyDecidedError(access.status)
        if (
            cleaned["decision"] == AccessStatus.APPROVED
            and access.expires_on is not None
            and access.expires_on < timezone.localdate()
        ):
            raise AccessRequestExpiredError(access.expires_on)

        access.status = cleaned["decision"]
        access.approver = approver
        access.decided_at = timezone.now()
        access.save(update_fields=["status", "approver", "decided_at"])
        notify_access_decided(access)

    return access
