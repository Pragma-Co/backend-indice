from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from core.models import Document, File, Revision, RevisionStatus, Role
from core.services.revision_review_exceptions import (
    OutdatedRevisionError,
    OwnRevisionReviewError,
    RevisionAlreadyDecidedError,
    RevisionNotFoundError,
    RevisionReviewValidationError,
)

REVIEWER_ROLES = frozenset({Role.AUDITOR, Role.ADMIN})
DECISIONS = (RevisionStatus.APPROVED, RevisionStatus.REJECTED)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

JUSTIFICATION_MIN_LENGTH = 20
JUSTIFICATION_MAX_LENGTH = 1000


def is_revision_reviewer(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.role in REVIEWER_ROLES)


def _error(code, message):
    return {"code": code, "message": message}


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
        raise RevisionReviewValidationError(errors)
    return {"page": page, "page_size": page_size}


def pending_revisions():
    return (
        Revision.objects.filter(
            status=RevisionStatus.PENDING,
            document__document_type__active=True,
            document__archived_at__isnull=True,
        )
        .select_related(
            "author",
            "document__project",
            "document__discipline",
            "document__document_type",
        )
        .prefetch_related(Prefetch("files", queryset=File.objects.order_by("id")))
        .order_by("created_at", "id")
    )


def list_pending_revisions(params) -> dict:
    query = parse_pending_query(params)
    paginator = Paginator(pending_revisions(), query["page_size"])
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
        raise RevisionReviewValidationError(
            {"body": _error("invalid", "Request body must be a JSON object.")}
        )

    errors = {}
    decision = payload.get("decision")
    if decision is None or (isinstance(decision, str) and not decision.strip()):
        errors["decision"] = _error("required", "Decision is required.")
    elif not isinstance(decision, str) or decision.strip().upper() not in DECISIONS:
        errors["decision"] = _error(
            "invalid_choice", f"decision must be one of {[str(value) for value in DECISIONS]}."
        )
    else:
        decision = RevisionStatus(decision.strip().upper())

    justification = payload.get("justification")
    if justification is not None and not isinstance(justification, str):
        errors["justification"] = _error("invalid", "justification must be a string.")
        raise RevisionReviewValidationError(errors)
    justification = (justification or "").strip()

    if "decision" not in errors and decision == RevisionStatus.REJECTED and not justification:
        errors["justification"] = _error(
            "required", "Justification is required to reject a revision."
        )
    elif justification and len(justification) < JUSTIFICATION_MIN_LENGTH:
        errors["justification"] = _error(
            "too_short",
            f"Justification must have at least {JUSTIFICATION_MIN_LENGTH} characters.",
        )
    elif len(justification) > JUSTIFICATION_MAX_LENGTH:
        errors["justification"] = _error(
            "too_long",
            f"Justification must have at most {JUSTIFICATION_MAX_LENGTH} characters.",
        )

    if errors:
        raise RevisionReviewValidationError(errors)
    return {"decision": decision, "justification": justification}


def decide_revision(revision_id, reviewer, payload) -> tuple[Revision, Revision | None]:
    cleaned = validate_decision_payload(payload)

    with transaction.atomic():
        document_id = (
            Revision.objects.filter(
                pk=revision_id,
                document__document_type__active=True,
                document__archived_at__isnull=True,
            )
            .values_list("document_id", flat=True)
            .first()
        )
        if document_id is None:
            raise RevisionNotFoundError()
        document = Document.objects.select_for_update().get(pk=document_id)
        revision = Revision.objects.select_for_update().get(pk=revision_id)

        if revision.status != RevisionStatus.PENDING:
            raise RevisionAlreadyDecidedError(revision.status)
        if reviewer.pk in (revision.author_id, document.responsible_id):
            raise OwnRevisionReviewError()

        previous_revision = (
            Revision.objects.select_for_update()
            .filter(document_id=document_id, status=RevisionStatus.APPROVED)
            .first()
        )
        superseded_revision = None
        if cleaned["decision"] == RevisionStatus.APPROVED:
            if previous_revision is not None and previous_revision.version > revision.version:
                raise OutdatedRevisionError(previous_revision.version)
            if previous_revision is not None:
                previous_revision.status = RevisionStatus.OBSOLETE
                previous_revision.save(update_fields=["status"])
                superseded_revision = previous_revision
            document.updated_by = reviewer
            document.save(update_fields=["updated_by"])

        revision.status = cleaned["decision"]
        revision.auditor = reviewer
        revision.auditor_comment = cleaned["justification"]
        revision.audited_at = timezone.now()
        revision.save(update_fields=["status", "auditor", "auditor_comment", "audited_at"])

    revision.document = document
    return revision, superseded_revision
