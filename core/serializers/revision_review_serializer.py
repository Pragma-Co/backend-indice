from core.models import File, Revision
from core.services.document_code_service import revision_label


def _serialize_file(file: File) -> dict:
    return {
        "id": file.id,
        "original_name": file.original_name,
        "extension": file.extension,
        "mime_type": file.mime_type,
        "size_bytes": file.size_bytes,
        "revision_changed": file.revision_changed,
    }


def serialize_pending_revision(revision: Revision) -> dict:
    document = revision.document
    return {
        "id": revision.id,
        "version": revision.version,
        "revision": revision_label(revision.version),
        "status": revision.status,
        "change_description": revision.change_description,
        "issue_date": revision.issue_date.isoformat() if revision.issue_date else None,
        "created_at": revision.created_at.isoformat(),
        "author": {"id": revision.author_id, "name": revision.author.name},
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
        "files": [_serialize_file(file) for file in revision.files.all()],
    }


def serialize_pending_page(page: dict) -> dict:
    return {**page, "results": [serialize_pending_revision(item) for item in page["results"]]}


def serialize_revision_decision(revision: Revision, superseded: Revision | None) -> dict:
    return {
        "id": revision.id,
        "document_id": revision.document_id,
        "version": revision.version,
        "revision": revision_label(revision.version),
        "status": revision.status,
        "auditor": {"id": revision.auditor_id, "name": revision.auditor.name},
        "auditor_comment": revision.auditor_comment,
        "audited_at": revision.audited_at.isoformat(),
        "superseded_revision": None
        if superseded is None
        else {
            "id": superseded.id,
            "version": superseded.version,
            "revision": revision_label(superseded.version),
            "status": superseded.status,
        },
    }
