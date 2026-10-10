from django.db import transaction
from django.utils import timezone

from core.models import Document
from core.services.documents_exceptions import ArchivePermissionDeniedError, DocumentNotFoundError
from core.services.documents_service import (
    filter_documents,
    paginate_documents,
    parse_document_query,
    serialize_document,
)
from core.services.revision_review_service import REVIEWER_ROLES


def is_manager(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.role in REVIEWER_ROLES)


def can_archive_document(document, user) -> bool:
    if not is_manager(user):
        return False
    return document.document_areas.filter(area_id=user.area_id).exists()


def archive_document(document_id, user) -> Document:
    with transaction.atomic():
        document = (
            Document.objects.select_for_update(of=("self",))
            .filter(pk=document_id, document_type__active=True, archived_at__isnull=True)
            .first()
        )
        if document is None:
            raise DocumentNotFoundError()
        if not can_archive_document(document, user):
            raise ArchivePermissionDeniedError()
        document.archived_at = timezone.now()
        document.archived_by = user
        document.updated_by = user
        document.save(update_fields=["archived_at", "archived_by", "updated_by"])
    return document


def restore_document(document_id, user) -> Document:
    with transaction.atomic():
        document = (
            Document.objects.select_for_update(of=("self",))
            .filter(pk=document_id, document_type__active=True, archived_at__isnull=False)
            .first()
        )
        if document is None:
            raise DocumentNotFoundError()
        if not can_archive_document(document, user):
            raise ArchivePermissionDeniedError()
        document.archived_at = None
        document.archived_by = None
        document.updated_by = user
        document.save(update_fields=["archived_at", "archived_by", "updated_by"])
    return document


def _serialize_archived_item(document):
    return {
        **serialize_document(document),
        "archived_at": document.archived_at.isoformat(),
        "archived_by": {"id": document.archived_by_id, "name": document.archived_by.name},
    }


def list_archived_documents(user, params) -> dict:
    query = parse_document_query(params)
    queryset = (
        filter_documents(query, archived=True)
        .filter(document_areas__area_id=user.area_id)
        .select_related("archived_by")
        .order_by("-archived_at", "-id")
    )
    return paginate_documents(queryset, query, _serialize_archived_item)
