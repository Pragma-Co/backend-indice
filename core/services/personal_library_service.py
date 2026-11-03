from django.db.models import F, OuterRef, Subquery

from core.models import Document, Revision, SavedDocument
from core.services.documents_service import can_view_document, serialize_document


class SavedDocumentNotFoundError(Exception):
    pass


class LibraryAccessDeniedError(Exception):
    pass


def _available_document(document_id):
    return (
        Document.objects.filter(
            pk=document_id,
            archived_at__isnull=True,
            document_type__active=True,
        )
        .select_related("document_type", "discipline", "created_by", "updated_by")
        .prefetch_related("areas")
        .first()
    )


def save_document(user, document_id):
    document = _available_document(document_id)
    if document is None:
        raise SavedDocumentNotFoundError()
    if not can_view_document(document, user):
        raise LibraryAccessDeniedError()
    saved_document, created = SavedDocument.objects.get_or_create(user=user, document=document)
    return saved_document, created


def remove_document(user, document_id):
    deleted, _ = SavedDocument.objects.filter(user=user, document_id=document_id).delete()
    if not deleted:
        raise SavedDocumentNotFoundError()


def list_saved_documents(user):
    latest_revision = Revision.objects.filter(document=OuterRef("pk")).order_by("-version")
    documents = (
        Document.objects.filter(
            saved_by_users__user=user,
            archived_at__isnull=True,
            document_type__active=True,
        )
        .annotate(
            status=Subquery(latest_revision.values("status")[:1]),
            latest_version=Subquery(latest_revision.values("version")[:1]),
            saved_at=F("saved_by_users__created_at"),
        )
        .select_related("document_type", "discipline", "created_by", "updated_by")
        .prefetch_related("areas")
        .order_by("-saved_at", "-id")
    )
    results = []
    for document in documents:
        if can_view_document(document, user):
            results.append(
                {
                    **serialize_document(document),
                    "saved_at": document.saved_at.isoformat(),
                }
            )
    return {"count": len(results), "results": results}
