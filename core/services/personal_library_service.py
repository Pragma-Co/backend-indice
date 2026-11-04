from django.db.models import F, OuterRef, Q

from core.models import Document, SavedDocument
from core.services.documents_service import (
    filter_documents,
    paginate_documents,
    parse_document_query,
    serialize_document,
)


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
        .filter(Q(areas__active=True) | Q(areas__isnull=True))
        .select_related("document_type", "discipline", "created_by", "updated_by")
        .prefetch_related("areas")
        .first()
    )


def save_document(user, document_id):
    document = _available_document(document_id)
    if document is None:
        raise SavedDocumentNotFoundError()
    saved_document, created = SavedDocument.objects.get_or_create(user=user, document=document)
    return saved_document, created


def remove_document(user, document_id):
    SavedDocument.objects.filter(user=user, document_id=document_id).delete()


def _serialize_saved(document):
    return {**serialize_document(document), "saved_at": document.saved_at.isoformat()}


def list_saved_documents(user, params):
    query = parse_document_query(params)
    documents = (
        filter_documents(query, user=user)
        .filter(saved_by_users__user=user)
        .annotate(saved_at=F("saved_by_users__created_at"))
        .order_by("-saved_at", "-id")
    )
    return paginate_documents(documents, query, _serialize_saved)
