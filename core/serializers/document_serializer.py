from core.models import AccessStatus, Document
from core.services.document_code_service import revision_label


def serialize_created_document(document: Document) -> dict:
    revision = document.revisions.order_by("-version").first()
    files = list(revision.files.all()) if revision is not None else []
    file = files[0] if files else None
    return {
        "id": document.id,
        "code": document.code,
        "title": document.title,
        "description": document.description,
        "project": {
            "id": document.project.id,
            "code": document.project.code,
            "name": document.project.name,
        },
        "discipline": {
            "id": document.discipline.id,
            "code": document.discipline.code,
            "name": document.discipline.name,
        },
        "document_type": {
            "code": document.document_type.code,
            "name": document.document_type.name,
        },
        "confidentiality": document.confidentiality_level,
        "responsible": {
            "id": document.responsible.id,
            "name": document.responsible.name,
            "email": document.responsible.email,
        },
        "areas": [
            {"acronym": area.acronym, "name": area.name}
            for area in document.areas.order_by("acronym")
        ],
        "authorized_groups": [
            {"id": grant.group.id, "name": grant.group.name}
            for grant in document.group_grants.select_related("group").order_by("group__name")
        ],
        "authorized_users": [
            {"id": access.user.id, "name": access.user.name, "email": access.user.email}
            for access in document.accesses.filter(status=AccessStatus.APPROVED)
            .select_related("user")
            .order_by("user__name", "user_id")
        ],
        "revision": None
        if revision is None
        else {
            "version": revision.version,
            "label": revision_label(revision.version),
            "status": revision.status,
            "issue_date": revision.issue_date.isoformat() if revision.issue_date else None,
        },
        "file": None
        if file is None
        else {
            "original_name": file.original_name,
            "extension": file.extension,
            "mime_type": file.mime_type,
            "size_bytes": file.size_bytes,
            "sha256": file.sha256,
            "storage_path": file.storage_path,
        },
        "files": [
            {
                "original_name": item.original_name,
                "extension": item.extension,
                "mime_type": item.mime_type,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "storage_path": item.storage_path,
            }
            for item in files
        ],
        "created_at": document.created_at.isoformat(),
    }


def serialize_archived_document(document: Document) -> dict:
    return {
        "id": document.id,
        "code": document.code,
        "archived_at": document.archived_at.isoformat(),
        "archived_by": {"id": document.archived_by.id, "name": document.archived_by.name},
    }


def serialize_restored_document(document: Document) -> dict:
    return {
        "id": document.id,
        "code": document.code,
        "archived_at": None,
        "restored_by": {"id": document.updated_by.id, "name": document.updated_by.name},
    }
