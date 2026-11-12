from pathlib import Path

from django.utils import timezone


def _iso(value):
    return value.isoformat() if value else None


def _user(user):
    return None if user is None else {"id": user.id, "name": user.name}


def serialize_incident_summary(incident):
    due_at = incident.authority_notification_due_at
    return {
        "id": incident.id,
        "reference": incident.reference,
        "title": incident.title,
        "incident_type": incident.incident_type,
        "severity": incident.severity,
        "status": incident.status,
        "occurred_at": _iso(incident.occurred_at),
        "detected_at": _iso(incident.detected_at),
        "reported_at": _iso(incident.reported_at),
        "affected_data_categories": list(incident.affected_data_categories),
        "affected_subjects_count": incident.affected_subjects_count,
        "reported_by": _user(incident.reported_by),
        "assigned_to": _user(incident.assigned_to),
        "authority_notification": {
            "required": incident.authority_notification_required,
            "due_at": _iso(due_at),
            "notified_at": _iso(incident.authority_notified_at),
            "overdue": bool(
                incident.authority_notification_required
                and incident.authority_notified_at is None
                and due_at is not None
                and due_at < timezone.now()
            ),
        },
        "subjects_notified_at": _iso(incident.subjects_notified_at),
        "resolved_at": _iso(incident.resolved_at),
        "closed_at": _iso(incident.closed_at),
    }


def serialize_action(action):
    return {
        "id": action.id,
        "kind": action.kind,
        "description": action.description,
        "performed_at": _iso(action.performed_at),
        "performed_by": _user(action.performed_by),
        "recorded_by": _user(action.recorded_by),
        "created_at": _iso(action.created_at),
    }


def serialize_status_change(change):
    return {
        "id": change.id,
        "from_status": change.from_status or None,
        "to_status": change.to_status,
        "note": change.note,
        "changed_by": _user(change.changed_by),
        "changed_at": _iso(change.changed_at),
    }


def serialize_incident_detail(incident):
    return {
        **serialize_incident_summary(incident),
        "description": incident.description,
        "root_cause": incident.root_cause,
        "affected_users": [_user(user) for user in incident.affected_users.all()],
        "affected_documents": [
            {"id": document.id, "code": document.code, "title": document.title}
            for document in incident.affected_documents.all()
        ],
        "actions": [serialize_action(action) for action in incident.actions.all()],
        "status_changes": [
            serialize_status_change(change) for change in incident.status_changes.all()
        ],
        "updated_at": _iso(incident.updated_at),
    }


def serialize_subject_notification(row):
    return {
        "user": _user(row.user),
        "reason": row.reason,
        "status": row.status,
        "attempts": row.attempts,
        "last_attempt_at": _iso(row.last_attempt_at),
        "sent_at": _iso(row.sent_at),
        "last_error": row.last_error or None,
    }


def serialize_subject_notifications(overview):
    incident = overview["incident"]
    payload = {
        "incident": {
            "id": incident.id,
            "reference": incident.reference,
            "status": incident.status,
            "subjects_notified_at": _iso(incident.subjects_notified_at),
        },
        "summary": overview["summary"],
        "recipients": [serialize_subject_notification(row) for row in overview["recipients"]],
        "preview": {"subject": overview["preview"]["subject"], "text": overview["preview"]["text"]},
    }
    if "outcome" in overview:
        payload["result"] = overview["outcome"]
    return payload


def serialize_backup_run(run):
    return {
        "id": run.id,
        "target": run.target,
        "status": run.status,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "file_name": Path(run.destination).name if run.destination else None,
        "size_bytes": run.size_bytes,
        "sha256": run.sha256 or None,
        "encrypted": run.encrypted,
        "record_count": run.record_count,
        "error": run.error or None,
        "pruned_at": _iso(run.pruned_at),
        "triggered_by": _user(run.triggered_by),
    }
