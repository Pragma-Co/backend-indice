from core.models import Document
from core.services.document_code_service import revision_label


def serialize_created_document(document: Document) -> dict:
    revision = document.revisions.order_by("-version").first()
    file = revision.files.first() if revision is not None else None
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
        "created_at": document.created_at.isoformat(),
    }
