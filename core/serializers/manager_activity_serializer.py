from core.models import AuditLog


def _serialize_user(entry: AuditLog) -> dict | None:
    if entry.user_id is None or entry.user is None:
        return None
    return {"id": entry.user_id, "name": entry.user.name}


def _serialize_document(document, code) -> dict | None:
    if document is not None:
        return {"id": document.pk, "code": document.code, "title": document.title}
    if code:
        return {"id": None, "code": code, "title": None}
    return None


def serialize_activity(entry: AuditLog, description: dict) -> dict:
    return {
        "id": entry.pk,
        "timestamp": entry.occurred_at.isoformat(),
        "user": _serialize_user(entry),
        "document": _serialize_document(description["document"], description["code"]),
        "file": description["file"],
        "revision": description["revision"],
        "event_type": description["event_type"],
        "event": description["event"],
        "status": description["status"],
        "detail": description["detail"],
    }


def serialize_activity_page(page: dict, descriptions: dict) -> dict:
    return {
        **page,
        "results": [serialize_activity(entry, descriptions[entry.pk]) for entry in page["results"]],
    }
