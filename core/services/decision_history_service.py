from datetime import date, datetime, time, timedelta

from django.core.paginator import Paginator
from django.utils import timezone

from core.models import AuditAction, AuditLog, Role
from core.serializers.decision_history_serializer import serialize_decision_page
from core.services.document_code_service import revision_label
from core.services.manager_activity_exceptions import ActivityQueryError
from core.services.manager_activity_service import (
    DEFAULT_PAGE_SIZE,
    ENTITY_DOCUMENT_ACCESS,
    ENTITY_REVISION,
    MAX_PAGE_SIZE,
    _error,
    _load_references,
    _positive_int,
)

REVISION_REQUEST = "REVISION"
ACCESS_REQUEST = "ACCESS"
REQUEST_TYPES = (REVISION_REQUEST, ACCESS_REQUEST)

APPROVED = "APPROVED"
REJECTED = "REJECTED"
DECISIONS = (APPROVED, REJECTED)

ENTITY_BY_REQUEST_TYPE = {
    REVISION_REQUEST: ENTITY_REVISION,
    ACCESS_REQUEST: ENTITY_DOCUMENT_ACCESS,
}


def _choice(params, name, choices, errors):
    value = (params.get(name) or "").strip().upper()
    if not value:
        return None
    if value not in choices:
        errors[name] = _error("invalid_choice", f"{name} must be one of {list(choices)}.")
        return None
    return value


def _day(params, name, errors):
    raw = (params.get(name) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors[name] = _error("invalid", f"{name} must be a date in the YYYY-MM-DD format.")
        return None


def parse_decision_history_query(params) -> dict:
    errors = {}
    page = _positive_int(params, "page", 1, errors)
    page_size = _positive_int(params, "page_size", DEFAULT_PAGE_SIZE, errors)
    if page_size > MAX_PAGE_SIZE:
        errors["page_size"] = _error("too_large", f"page_size must be at most {MAX_PAGE_SIZE}.")
    request_type = _choice(params, "request_type", REQUEST_TYPES, errors)
    decision = _choice(params, "decision", DECISIONS, errors)
    date_from = _day(params, "date_from", errors)
    date_to = _day(params, "date_to", errors)
    if date_from and date_to and date_from > date_to:
        errors["date_to"] = _error("invalid_range", "date_to must not be before date_from.")
    if errors:
        raise ActivityQueryError(errors)
    return {
        "page": page,
        "page_size": page_size,
        "request_type": request_type,
        "decision": decision,
        "date_from": date_from,
        "date_to": date_to,
    }


def _start_of_day(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def decision_events(request_type=None, decision=None):
    return [
        f"{kind}_{outcome}"
        for kind in ([request_type] if request_type else REQUEST_TYPES)
        for outcome in ([decision] if decision else DECISIONS)
    ]


def decision_entries(manager, query):
    entries = AuditLog.objects.filter(
        action=AuditAction.UPDATE,
        entity__in=ENTITY_BY_REQUEST_TYPE.values(),
        record__event__in=decision_events(query["request_type"], query["decision"]),
    )
    if manager.role != Role.ADMIN:
        # Reviewers decide on documents of any area: the team is whoever decided
        entries = entries.filter(user__area_id=manager.area_id)
    if query["date_from"]:
        entries = entries.filter(occurred_at__gte=_start_of_day(query["date_from"]))
    if query["date_to"]:
        entries = entries.filter(
            occurred_at__lt=_start_of_day(query["date_to"] + timedelta(days=1))
        )
    return entries.select_related("user").order_by("-occurred_at", "-id")


def describe_decision(entry, references) -> dict:
    record = entry.record or {}
    request_type, _, decision = record["event"].partition("_")
    if entry.entity == ENTITY_REVISION:
        revision = references["revisions"].get(entry.entity_id)
        document = revision.document if revision else None
        requester = revision.author if revision else None
        version = record.get("version") or (revision.version if revision else None)
    else:
        access = references["accesses"].get(entry.entity_id)
        document = access.document if access else None
        requester = access.user if access else None
        version = None
    reason = (
        record.get("justification") if entry.entity == ENTITY_REVISION else record.get("opinion")
    )
    return {
        "request_type": request_type,
        "decision": decision,
        "document": document,
        "code": document.code if document else record.get("document_code"),
        "revision": revision_label(version) if version is not None else None,
        "requester": requester,
        "reason": (reason or "").strip() or None,
    }


def list_decision_history(manager, params) -> dict:
    query = parse_decision_history_query(params)
    paginator = Paginator(decision_entries(manager, query), query["page_size"])
    page_number = query["page"]
    entries = (
        list(paginator.page(page_number).object_list) if page_number <= paginator.num_pages else []
    )
    references = _load_references(entries)
    descriptions = {entry.pk: describe_decision(entry, references) for entry in entries}
    return serialize_decision_page(
        {
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_number,
            "page_size": query["page_size"],
            "results": entries,
        },
        descriptions,
    )
