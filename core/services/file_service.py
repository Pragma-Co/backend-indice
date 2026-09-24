from pathlib import Path

from django.conf import settings

from core.models import Document
from core.models.revision import File
from core.services.documents_exceptions import AccessDeniedError, DocumentFileNotFoundError
from core.services.documents_service import can_view_document, resolve_user


def _get_document_for_file(file_obj):
    return (
        Document.objects.filter(document_type__active=True)
        .select_related("responsible")
        .prefetch_related("revisions")
        .filter(pk=file_obj.revision.document_id)
        .first()
    )


def get_document_file_for_view(file_id, user_id=None):
    file_obj = File.objects.select_related("revision").filter(pk=file_id).first()
    if file_obj is None:
        raise DocumentFileNotFoundError()

    document = _get_document_for_file(file_obj)
    if document is None:
        raise DocumentFileNotFoundError()

    user = resolve_user(user_id)
    if not can_view_document(document, user):
        raise AccessDeniedError(document, user)

    path = Path(settings.DOCUMENT_STORAGE_DIR) / file_obj.storage_path
    if not path.is_file():
        raise DocumentFileNotFoundError()
    return file_obj, path
