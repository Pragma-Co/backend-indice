import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.models import AuditAction
from core.serializers.data_incident_serializer import (
    serialize_action,
    serialize_backup_run,
    serialize_incident_detail,
    serialize_incident_summary,
    serialize_subject_notifications,
)
from core.services import audit_service
from core.services.backup_service import BackupQueryError, list_backup_runs
from core.services.data_incident_exceptions import (
    IncidentClosedError,
    IncidentClosureBlockedError,
    IncidentNotFoundError,
    IncidentQueryError,
    IncidentValidationError,
    InvalidStatusTransitionError,
    NoAffectedUsersError,
)
from core.services.data_incident_service import (
    add_action,
    change_status,
    get_incident,
    is_security_officer,
    list_incidents,
    record_notification,
    register_incident,
    update_incident,
)
from core.services.incident_subject_notification_service import (
    notify_affected_users,
    subject_notifications_overview,
)

logger = logging.getLogger(__name__)

ENTITY_INCIDENT = "data_incident"
ENTITY_BACKUP_RUN = "backup_run"


def _security_officer(request):
    user = request.user
    if not (user.is_authenticated and user.is_active):
        return None, JsonResponse({"error": "AuthenticationRequired"}, status=401)
    if not is_security_officer(user):
        return None, JsonResponse({"error": "PermissionDenied"}, status=403)
    return user, None


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _error_response(exc):
    if isinstance(exc, IncidentValidationError):
        return JsonResponse({"errors": exc.errors}, status=400)
    if isinstance(exc, IncidentNotFoundError):
        return JsonResponse({"error": "IncidentNotFound"}, status=404)
    if isinstance(exc, IncidentClosedError):
        return JsonResponse({"error": "IncidentClosed"}, status=409)
    if isinstance(exc, InvalidStatusTransitionError):
        return JsonResponse({"error": "InvalidStatusTransition", "status": exc.current}, status=409)
    if isinstance(exc, IncidentClosureBlockedError):
        return JsonResponse({"error": "IncidentClosureBlocked", "reasons": exc.reasons}, status=409)
    if isinstance(exc, NoAffectedUsersError):
        return JsonResponse({"error": "NoAffectedUsers"}, status=409)
    if isinstance(exc, audit_service.AuditLogWriteError):
        return JsonResponse({"error": "AuditUnavailable"}, status=503)
    return None


def _write(request, operation, action, event, details_for):
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "InvalidJSON"}, status=400)
    try:
        with transaction.atomic():
            result = operation(body)
            incident_id, details, response = details_for(result)
            audit_service.log_event_required(
                request, action, ENTITY_INCIDENT, incident_id, {"event": event, **details}
            )
    except Exception as exc:
        response = _error_response(exc)
        if response is None:
            logger.exception("Failed to %s", event.lower())
            return JsonResponse({"error": type(exc).__name__}, status=500)
        return response
    return response


def _register(request, user):
    def details_for(incident):
        details = {
            "reference": incident.reference,
            "incident_type": incident.incident_type,
            "severity": incident.severity,
        }
        response = JsonResponse(serialize_incident_detail(get_incident(incident.pk)), status=201)
        return incident.pk, details, response

    return _write(
        request,
        lambda body: register_incident(body, user),
        AuditAction.CREATE,
        "INCIDENT_REGISTERED",
        details_for,
    )


def _list(request, user):
    try:
        payload = list_incidents(request.GET, serialize_incident_summary)
    except IncidentQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list incidents")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    audit_service.log_event(
        request,
        AuditAction.READ,
        ENTITY_INCIDENT,
        None,
        {"event": "INCIDENT_LIST_VIEWED", "filters": dict(request.GET.items())},
    )
    return JsonResponse(payload)


@require_http_methods(["GET", "POST"])
def incidents_collection(request):
    user, error_response = _security_officer(request)
    if error_response is not None:
        return error_response
    if request.method == "POST":
        return _register(request, user)
    return _list(request, user)


def _detail(request, incident_id):
    try:
        incident = get_incident(incident_id)
    except IncidentNotFoundError:
        return JsonResponse({"error": "IncidentNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to retrieve incident")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    audit_service.log_event(
        request,
        AuditAction.READ,
        ENTITY_INCIDENT,
        incident.pk,
        {"event": "INCIDENT_VIEWED", "reference": incident.reference},
    )
    return JsonResponse(serialize_incident_detail(incident))


def _update(request, user, incident_id):
    def details_for(result):
        incident, changed = result
        response = JsonResponse(serialize_incident_detail(get_incident(incident.pk)))
        return incident.pk, {"reference": incident.reference, "fields": changed}, response

    return _write(
        request,
        lambda body: update_incident(incident_id, body, user),
        AuditAction.UPDATE,
        "INCIDENT_UPDATED",
        details_for,
    )


@require_http_methods(["GET", "PATCH"])
def incident_resource(request, incident_id):
    user, error_response = _security_officer(request)
    if error_response is not None:
        return error_response
    if request.method == "PATCH":
        return _update(request, user, incident_id)
    return _detail(request, incident_id)


@require_POST
def incident_actions_view(request, incident_id):
    user, error_response = _security_officer(request)
    if error_response is not None:
        return error_response

    def details_for(action):
        details = {
            "reference": action.incident.reference,
            "kind": action.kind,
            "action_id": action.pk,
        }
        return action.incident_id, details, JsonResponse(serialize_action(action), status=201)

    return _write(
        request,
        lambda body: add_action(incident_id, body, user),
        AuditAction.UPDATE,
        "INCIDENT_ACTION_RECORDED",
        details_for,
    )


@require_POST
def incident_status_view(request, incident_id):
    user, error_response = _security_officer(request)
    if error_response is not None:
        return error_response
    previous = {"status": None}

    def operation(body):
        current = get_incident(incident_id)
        previous["status"] = current.status
        return change_status(incident_id, body, user)

    def details_for(incident):
        details = {
            "reference": incident.reference,
            "from_status": previous["status"],
            "to_status": incident.status,
        }
        return (
            incident.pk,
            details,
            JsonResponse(serialize_incident_detail(get_incident(incident.pk))),
        )

    return _write(request, operation, AuditAction.UPDATE, "INCIDENT_STATUS_CHANGED", details_for)


@require_POST
def incident_notifications_view(request, incident_id):
    user, error_response = _security_officer(request)
    if error_response is not None:
        return error_response

    def details_for(incident):
        body = _json_body(request) or {}
        details = {"reference": incident.reference, "recipient": body.get("recipient")}
        return (
            incident.pk,
            details,
            JsonResponse(serialize_incident_detail(get_incident(incident.pk))),
        )

    return _write(
        request,
        lambda body: record_notification(incident_id, body, user),
        AuditAction.UPDATE,
        "INCIDENT_NOTIFICATION_RECORDED",
        details_for,
    )


def _subject_notifications_overview(request, incident_id):
    try:
        overview = subject_notifications_overview(incident_id)
    except IncidentNotFoundError:
        return JsonResponse({"error": "IncidentNotFound"}, status=404)
    except Exception as exc:
        logger.exception("Failed to list the subject notifications")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    incident = overview["incident"]
    audit_service.log_event(
        request,
        AuditAction.READ,
        ENTITY_INCIDENT,
        incident.pk,
        {"event": "INCIDENT_SUBJECT_NOTIFICATIONS_VIEWED", "reference": incident.reference},
    )
    return JsonResponse(serialize_subject_notifications(overview))


def _notify_subjects(request, incident_id):
    try:
        result = notify_affected_users(incident_id)
    except Exception as exc:
        response = _error_response(exc)
        if response is None:
            logger.exception("Failed to notify the affected users")
            return JsonResponse({"error": type(exc).__name__}, status=500)
        return response
    incident = result["incident"]
    try:
        audit_service.log_event_required(
            request,
            AuditAction.UPDATE,
            ENTITY_INCIDENT,
            incident.pk,
            {
                "event": "INCIDENT_SUBJECTS_NOTIFIED",
                "reference": incident.reference,
                **result["outcome"],
            },
        )
    except audit_service.AuditLogWriteError:
        return JsonResponse({"error": "AuditUnavailable"}, status=503)
    return JsonResponse(serialize_subject_notifications(result))


@require_http_methods(["GET", "POST"])
def incident_subject_notifications_view(request, incident_id):
    user, error_response = _security_officer(request)
    if error_response is not None:
        return error_response
    if request.method == "POST":
        return _notify_subjects(request, incident_id)
    return _subject_notifications_overview(request, incident_id)


@require_GET
def backup_runs_view(request):
    user, error_response = _security_officer(request)
    if error_response is not None:
        return error_response
    try:
        payload = list_backup_runs(request.GET, serialize_backup_run)
    except BackupQueryError as exc:
        return JsonResponse({"errors": exc.errors}, status=400)
    except Exception as exc:
        logger.exception("Failed to list backup runs")
        return JsonResponse({"error": type(exc).__name__}, status=500)
    audit_service.log_event(
        request, AuditAction.READ, ENTITY_BACKUP_RUN, None, {"event": "BACKUP_HISTORY_VIEWED"}
    )
    return JsonResponse(payload)
