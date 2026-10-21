from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import AccessStatus, Area, Document, DocumentAccess
from core.services.access_request_exceptions import (
    AccessRequestAlreadyDecidedError,
    AccessRequestNotFoundError,
    AccessRequestValidationError,
    OwnAccessRequestReviewError,
)

DECISIONS = (AccessStatus.APPROVED, AccessStatus.REJECTED)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _error(code, message):
    return {"code": code, "message": message}


def decidable_documents(approver):
    return Document.objects.filter(document_type__active=True).filter(
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

        access.status = cleaned["decision"]
        access.approver = approver
        access.decided_at = timezone.now()
        access.save(update_fields=["status", "approver", "decided_at"])

    return access
