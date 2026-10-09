from django.db import transaction
from django.utils import timezone

from core.models import Document
from core.services.documents_exceptions import ArchivePermissionDeniedError, DocumentNotFoundError
from core.services.revision_review_service import REVIEWER_ROLES


def can_archive_document(document, user) -> bool:
    if user is None or not user.is_active or user.role not in REVIEWER_ROLES:
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
