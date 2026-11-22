from core.models import AuditLog


def _serialize_person(user) -> dict | None:
    return {"id": user.pk, "name": user.name} if user is not None else None


def _serialize_document(description: dict) -> dict | None:
    document, code = description["document"], description["code"]
    if document is not None:
        return {"id": document.pk, "code": document.code, "title": document.title}
    if code:
        return {"id": None, "code": code, "title": None}
    return None


def serialize_decision(entry: AuditLog, description: dict) -> dict:
    return {
        "id": entry.pk,
        "timestamp": entry.occurred_at.isoformat(),
        "request_type": description["request_type"],
        "decision": description["decision"],
        "document": _serialize_document(description),
        "revision": description["revision"],
        "requester": _serialize_person(description["requester"]),
        "user": _serialize_person(entry.user),
        "reason": description["reason"],
    }


def serialize_decision_page(page: dict, descriptions: dict) -> dict:
    return {
        **page,
        "results": [serialize_decision(entry, descriptions[entry.pk]) for entry in page["results"]],
    }
