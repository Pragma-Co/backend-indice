from core.models import DocumentAccess


def _isoformat(value):
    return value.isoformat() if value else None


def serialize_pending_access_request(access: DocumentAccess) -> dict:
    document = access.document
    requester = access.user
    return {
        "id": access.id,
        "status": access.status,
        "justification": access.justification,
        "requested_at": _isoformat(access.requested_at),
        "requester": {
            "id": requester.id,
            "name": requester.name,
            "area": {"acronym": requester.area.acronym, "name": requester.area.name},
        },
        "document": {
            "id": document.id,
            "code": document.code,
            "title": document.title,
            "confidentiality_level": document.confidentiality_level,
            "project": {"code": document.project.code, "name": document.project.name},
            "discipline": {"code": document.discipline.code, "name": document.discipline.name},
            "document_type": {
                "code": document.document_type.code,
                "name": document.document_type.name,
            },
        },
    }


def serialize_pending_access_page(page: dict) -> dict:
    return {
        **page,
        "results": [serialize_pending_access_request(item) for item in page["results"]],
    }


def serialize_access_decision(access: DocumentAccess) -> dict:
    return {
        "id": access.id,
        "document_id": access.document_id,
        "requester": {"id": access.user_id, "name": access.user.name},
        "status": access.status,
        "approver": {"id": access.approver_id, "name": access.approver.name},
        "requested_at": _isoformat(access.requested_at),
        "decided_at": _isoformat(access.decided_at),
    }
