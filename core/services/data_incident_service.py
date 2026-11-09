from datetime import timedelta

from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    DataIncident,
    DataIncidentAction,
    DataIncidentAffectedDocument,
    DataIncidentAffectedUser,
    DataIncidentStatusChange,
    Document,
    Role,
    User,
)
from core.models.choices import (
    IncidentActionKind,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    NotificationRecipient,
    PersonalDataCategory,
)
from core.services.data_incident_exceptions import (
    IncidentClosedError,
    IncidentClosureBlockedError,
    IncidentNotFoundError,
    IncidentQueryError,
    IncidentReferenceCollisionError,
    IncidentValidationError,
    InvalidStatusTransitionError,
)

AUTHORITY_NOTIFICATION_BUSINESS_DAYS = 3
SEVERITIES_REQUIRING_AUTHORITY_NOTIFICATION = frozenset(
    {IncidentSeverity.HIGH, IncidentSeverity.CRITICAL}
)
STATUS_TRANSITIONS = {
    IncidentStatus.REPORTED: frozenset({IncidentStatus.CONTAINMENT, IncidentStatus.ANALYSIS}),
    IncidentStatus.CONTAINMENT: frozenset({IncidentStatus.ANALYSIS}),
    IncidentStatus.ANALYSIS: frozenset({IncidentStatus.CONTAINMENT, IncidentStatus.RESOLVED}),
    IncidentStatus.RESOLVED: frozenset({IncidentStatus.ANALYSIS, IncidentStatus.CLOSED}),
    IncidentStatus.CLOSED: frozenset(),
}
CLOSURE_NO_ACTIONS = "no_actions_recorded"
CLOSURE_AUTHORITY_NOT_NOTIFIED = "authority_not_notified"
TITLE_MAX_LENGTH = 200
REFERENCE_PREFIX = "INC"
REFERENCE_ATTEMPTS = 5
FUTURE_TOLERANCE = timedelta(minutes=5)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
UPDATABLE_FIELDS = (
    "severity",
    "root_cause",
    "assigned_to_id",
    "authority_notification_required",
    "affected_subjects_count",
    "affected_data_categories",
)


def is_security_officer(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.role == Role.ADMIN)


def add_business_days(moment, days):
    local = timezone.localtime(moment)
    remaining = days
    while remaining > 0:
        local += timedelta(days=1)
        if local.weekday() < 5:
            remaining -= 1
    return local


def _error(code, message):
    return {"code": code, "message": message}


def _text(payload, field, errors, required=True, max_length=None):
    value = payload.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            errors[field] = _error("required", f"{field} is required.")
        return "" if value is None or isinstance(value, str) else None
    if not isinstance(value, str):
        errors[field] = _error("invalid", f"{field} must be a string.")
        return None
    value = value.strip()
    if max_length and len(value) > max_length:
        errors[field] = _error("too_long", f"{field} must have at most {max_length} characters.")
    return value


def _choice(payload, field, choices, errors, required=True, default=None):
    value = payload.get(field, default)
    if value is None or value == "":
        if required:
            errors[field] = _error("required", f"{field} is required.")
        return default
    if value not in choices.values:
        errors[field] = _error("invalid_choice", f"{field} must be one of {list(choices.values)}.")
        return default
    return choices(value)


def _datetime(payload, field, errors, required=True, default=None):
    raw = payload.get(field)
    if raw is None or raw == "":
        if required and default is None:
            errors[field] = _error("required", f"{field} is required.")
        return default
    parsed = parse_datetime(raw) if isinstance(raw, str) else None
    if parsed is None:
        errors[field] = _error("invalid", f"{field} must be an ISO 8601 datetime.")
        return default
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    if parsed > timezone.now() + FUTURE_TOLERANCE:
        errors[field] = _error("in_the_future", f"{field} cannot be in the future.")
        return default
    return parsed


def _boolean(payload, field, errors, default):
    value = payload.get(field)
    if value is None:
        return default
    if not isinstance(value, bool):
        errors[field] = _error("invalid", f"{field} must be a boolean.")
        return default
    return value


def _non_negative_int(payload, field, errors, default=0):
    value = payload.get(field)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors[field] = _error("invalid", f"{field} must be a non-negative integer.")
        return default
    return value


def _categories(payload, errors, required=True, default=None):
    value = payload.get("affected_data_categories")
    if value is None:
        if required:
            errors["affected_data_categories"] = _error(
                "required", "affected_data_categories is required."
            )
        return default
    if not isinstance(value, list) or not value:
        errors["affected_data_categories"] = _error(
            "invalid", "affected_data_categories must be a non-empty list."
        )
        return default
    unknown = [item for item in value if item not in PersonalDataCategory.values]
    if unknown:
        errors["affected_data_categories"] = _error(
            "invalid_choice",
            f"affected_data_categories must be among {list(PersonalDataCategory.values)}.",
        )
        return default
    return list(dict.fromkeys(value))


def _existing_ids(payload, field, queryset, errors):
    value = payload.get(field)
    if value is None:
        return []
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        errors[field] = _error("invalid", f"{field} must be a list of integer ids.")
        return []
    ids = list(dict.fromkeys(value))
    found = set(queryset.filter(pk__in=ids).values_list("pk", flat=True))
    missing = [item for item in ids if item not in found]
    if missing:
        errors[field] = _error("not_found", f"{field} contains unknown ids: {missing}.")
        return []
    return ids


def _assignee(payload, errors, field="assigned_to_id"):
    value = payload.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        errors[field] = _error("invalid", f"{field} must be an integer.")
        return None
    user = User.objects.filter(pk=value, is_active=True).first()
    if user is None or not is_security_officer(user):
        errors[field] = _error(
            "not_security_officer", "The responsible must be an active administrator."
        )
        return None
    return user


def _actor_user(payload, field, errors, default):
    value = payload.get(field)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        errors[field] = _error("invalid", f"{field} must be an integer.")
        return default
    user = User.objects.filter(pk=value, is_active=True).first()
    if user is None:
        errors[field] = _error("not_found", f"{field} is not an active user.")
        return default
    return user


def authority_deadline(detected_at, required):
    if not required:
        return None
    return add_business_days(detected_at, AUTHORITY_NOTIFICATION_BUSINESS_DAYS)


def next_reference(now):
    prefix = f"{REFERENCE_PREFIX}-{now.year}-"
    taken = DataIncident.objects.filter(reference__startswith=prefix).count()
    return f"{prefix}{taken + 1:04d}"


def _create_with_reference(fields):
    for _attempt in range(REFERENCE_ATTEMPTS):
        try:
            with transaction.atomic():
                return DataIncident.objects.create(
                    reference=next_reference(timezone.localtime()), **fields
                )
        except IntegrityError:
            continue
    raise IncidentReferenceCollisionError()


def register_incident(payload, reporter):
    if not isinstance(payload, dict):
        raise IncidentValidationError({"body": _error("invalid", "Body must be a JSON object.")})
    errors = {}
    title = _text(payload, "title", errors, max_length=TITLE_MAX_LENGTH)
    description = _text(payload, "description", errors)
    incident_type = _choice(payload, "incident_type", IncidentType, errors)
    severity = _choice(payload, "severity", IncidentSeverity, errors)
    occurred_at = _datetime(payload, "occurred_at", errors)
    detected_at = _datetime(payload, "detected_at", errors, default=timezone.now())
    categories = _categories(payload, errors)
    subjects_count = _non_negative_int(payload, "affected_subjects_count", errors)
    affected_user_ids = _existing_ids(payload, "affected_user_ids", User.objects.all(), errors)
    affected_document_ids = _existing_ids(
        payload, "affected_document_ids", Document.objects.all(), errors
    )
    assignee = _assignee(payload, errors)
    root_cause = _text(payload, "root_cause", errors, required=False) or ""
    required = _boolean(
        payload,
        "authority_notification_required",
        errors,
        severity in SEVERITIES_REQUIRING_AUTHORITY_NOTIFICATION,
    )
    if occurred_at and detected_at and detected_at < occurred_at:
        errors["detected_at"] = _error(
            "before_occurrence", "detected_at cannot be earlier than occurred_at."
        )
    if errors:
        raise IncidentValidationError(errors)

    with transaction.atomic():
        incident = _create_with_reference(
            {
                "title": title,
                "description": description,
                "incident_type": incident_type,
                "severity": severity,
                "occurred_at": occurred_at,
                "detected_at": detected_at,
                "affected_data_categories": categories,
                "affected_subjects_count": subjects_count,
                "reported_by": reporter,
                "assigned_to": assignee,
                "root_cause": root_cause,
                "authority_notification_required": required,
                "authority_notification_due_at": authority_deadline(detected_at, required),
            }
        )
        DataIncidentAffectedUser.objects.bulk_create(
            [DataIncidentAffectedUser(incident=incident, user_id=pk) for pk in affected_user_ids]
        )
        DataIncidentAffectedDocument.objects.bulk_create(
            [
                DataIncidentAffectedDocument(incident=incident, document_id=pk)
                for pk in affected_document_ids
            ]
        )
        DataIncidentStatusChange.objects.create(
            incident=incident,
            to_status=IncidentStatus.REPORTED,
            changed_by=reporter,
        )
    return incident


def get_incident(incident_id):
    incident = (
        DataIncident.objects.select_related("reported_by", "assigned_to")
        .prefetch_related(
            "affected_users",
            "affected_documents",
            Prefetch(
                "actions",
                queryset=DataIncidentAction.objects.select_related("performed_by", "recorded_by"),
            ),
            Prefetch(
                "status_changes",
                queryset=DataIncidentStatusChange.objects.select_related("changed_by"),
            ),
        )
        .filter(pk=incident_id)
        .first()
    )
    if incident is None:
        raise IncidentNotFoundError()
    return incident


def _open_incident(incident_id):
    incident = DataIncident.objects.filter(pk=incident_id).first()
    if incident is None:
        raise IncidentNotFoundError()
    if incident.status == IncidentStatus.CLOSED:
        raise IncidentClosedError()
    return incident


def add_action(incident_id, payload, actor):
    incident = _open_incident(incident_id)
    if not isinstance(payload, dict):
        raise IncidentValidationError({"body": _error("invalid", "Body must be a JSON object.")})
    errors = {}
    kind = _choice(payload, "kind", IncidentActionKind, errors)
    description = _text(payload, "description", errors)
    performed_at = _datetime(payload, "performed_at", errors, default=timezone.now())
    performed_by = _actor_user(payload, "performed_by_id", errors, actor)
    if errors:
        raise IncidentValidationError(errors)
    return DataIncidentAction.objects.create(
        incident=incident,
        kind=kind,
        description=description,
        performed_at=performed_at,
        performed_by=performed_by,
        recorded_by=actor,
    )


def closure_blockers(incident):
    reasons = []
    if not incident.actions.exists():
        reasons.append(CLOSURE_NO_ACTIONS)
    if incident.authority_notification_required and incident.authority_notified_at is None:
        reasons.append(CLOSURE_AUTHORITY_NOT_NOTIFIED)
    return reasons


def change_status(incident_id, payload, actor):
    incident = DataIncident.objects.filter(pk=incident_id).first()
    if incident is None:
        raise IncidentNotFoundError()
    if not isinstance(payload, dict):
        raise IncidentValidationError({"body": _error("invalid", "Body must be a JSON object.")})
    errors = {}
    requested = _choice(payload, "status", IncidentStatus, errors)
    note = _text(payload, "note", errors, required=False) or ""
    if errors:
        raise IncidentValidationError(errors)
    current = IncidentStatus(incident.status)
    if requested not in STATUS_TRANSITIONS[current]:
        raise InvalidStatusTransitionError(current, requested)
    if requested == IncidentStatus.CLOSED:
        blockers = closure_blockers(incident)
        if blockers:
            raise IncidentClosureBlockedError(blockers)

    now = timezone.now()
    with transaction.atomic():
        incident.status = requested
        if requested == IncidentStatus.RESOLVED:
            incident.resolved_at = now
        elif requested == IncidentStatus.CLOSED:
            incident.closed_at = now
        else:
            incident.resolved_at = None
        incident.save(update_fields=["status", "resolved_at", "closed_at", "updated_at"])
        DataIncidentStatusChange.objects.create(
            incident=incident,
            from_status=current,
            to_status=requested,
            note=note,
            changed_by=actor,
        )
    return incident


def record_notification(incident_id, payload, actor):
    incident = _open_incident(incident_id)
    if not isinstance(payload, dict):
        raise IncidentValidationError({"body": _error("invalid", "Body must be a JSON object.")})
    errors = {}
    recipient = _choice(payload, "recipient", NotificationRecipient, errors)
    notified_at = _datetime(payload, "notified_at", errors, default=timezone.now())
    if errors:
        raise IncidentValidationError(errors)
    if recipient == NotificationRecipient.AUTHORITY:
        incident.authority_notified_at = notified_at
        incident.save(update_fields=["authority_notified_at", "updated_at"])
    else:
        incident.subjects_notified_at = notified_at
        incident.save(update_fields=["subjects_notified_at", "updated_at"])
    return incident


def update_incident(incident_id, payload, actor):
    incident = _open_incident(incident_id)
    if not isinstance(payload, dict):
        raise IncidentValidationError({"body": _error("invalid", "Body must be a JSON object.")})
    unknown = sorted(set(payload) - set(UPDATABLE_FIELDS))
    if unknown:
        raise IncidentValidationError(
            {"body": _error("unknown_fields", f"Unknown fields: {unknown}.")}
        )
    errors = {}
    changed = []
    if "severity" in payload:
        incident.severity = _choice(payload, "severity", IncidentSeverity, errors)
        changed.append("severity")
    if "root_cause" in payload:
        incident.root_cause = _text(payload, "root_cause", errors, required=False) or ""
        changed.append("root_cause")
    if "assigned_to_id" in payload:
        incident.assigned_to = _assignee(payload, errors)
        changed.append("assigned_to")
    if "affected_subjects_count" in payload:
        incident.affected_subjects_count = _non_negative_int(
            payload, "affected_subjects_count", errors
        )
        changed.append("affected_subjects_count")
    if "affected_data_categories" in payload:
        incident.affected_data_categories = _categories(payload, errors, default=[])
        changed.append("affected_data_categories")
    if "authority_notification_required" in payload:
        incident.authority_notification_required = _boolean(
            payload, "authority_notification_required", errors, False
        )
        incident.authority_notification_due_at = authority_deadline(
            incident.detected_at, incident.authority_notification_required
        )
        changed.extend(["authority_notification_required", "authority_notification_due_at"])
    if errors:
        raise IncidentValidationError(errors)
    incident.save(update_fields=[*changed, "updated_at"])
    return incident, changed


def _positive_int(params, name, default, errors):
    raw = str(params.get(name, "") or "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        errors[name] = _error("invalid", f"{name} must be a positive integer.")
        return default
    return int(raw)


def _filter_choice(params, name, choices, errors):
    raw = str(params.get(name, "") or "").strip().upper()
    if not raw:
        return None
    if raw not in choices.values:
        errors[name] = _error("invalid_choice", f"{name} must be one of {list(choices.values)}.")
        return None
    return raw


def parse_incident_query(params):
    errors = {}
    query = {
        "page": _positive_int(params, "page", 1, errors),
        "page_size": min(
            _positive_int(params, "page_size", DEFAULT_PAGE_SIZE, errors), MAX_PAGE_SIZE
        ),
        "status": _filter_choice(params, "status", IncidentStatus, errors),
        "severity": _filter_choice(params, "severity", IncidentSeverity, errors),
        "type": _filter_choice(params, "type", IncidentType, errors),
        "overdue": str(params.get("overdue", "") or "").strip().lower() == "true",
    }
    if errors:
        raise IncidentQueryError(errors)
    return query


def list_incidents(params, serialize):
    query = parse_incident_query(params)
    queryset = DataIncident.objects.select_related("reported_by", "assigned_to")
    if query["status"]:
        queryset = queryset.filter(status=query["status"])
    if query["severity"]:
        queryset = queryset.filter(severity=query["severity"])
    if query["type"]:
        queryset = queryset.filter(incident_type=query["type"])
    if query["overdue"]:
        queryset = queryset.filter(
            authority_notification_required=True,
            authority_notified_at__isnull=True,
            authority_notification_due_at__lt=timezone.now(),
        )
    paginator = Paginator(queryset, query["page_size"])
    page_number = query["page"]
    items = paginator.page(page_number) if page_number <= paginator.num_pages else []
    return {
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_number,
        "page_size": query["page_size"],
        "results": [serialize(incident) for incident in items],
    }
