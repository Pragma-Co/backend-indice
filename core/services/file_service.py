"""Service layer for streaming document files for preview."""

from core.models import Document, DocumentAccess, User
from core.models.choices import AccessStatus, RevisionStatus
from core.models.revision import File
from core.services.documents_exceptions import DocumentFilePermissionError


class DocumentFileNotFoundError(Exception):
    """Arquivo inexistente."""


def _get_document_for_file(file_obj):
    revision = file_obj.revision
    if revision is None:
        return None
    return (
        Document.objects.filter(document_type__active=True)
        .select_related("responsible", "project", "discipline", "document_type")
        .filter(pk=revision.document_id)
        .first()
    )


def _get_current_revision(document):
    revisions = list(document.revisions.all())
    if not revisions:
        return None
    for revision in revisions:
        if revision.status == RevisionStatus.APPROVED:
            return revision
    return revisions[0]


def _user_can_view(document, user):
    if user is None:
        return False

    if document.responsible_id == user.id:
        return True

    if DocumentAccess.objects.filter(
        document=document, user=user, status=AccessStatus.APPROVED
    ).exists():
        return True

    current_revision = _get_current_revision(document)
    return (
        current_revision is not None
        and current_revision.status == RevisionStatus.APPROVED
    )


def get_document_file_for_view(file_id, user_id=None):
    """Busca o arquivo e valida o acesso antes de servir inline."""
    file_obj = (
        File.objects.select_related("revision", "revision__document")
        .filter(pk=file_id)
        .first()
    )
    if file_obj is None:
        raise DocumentFileNotFoundError()

    document = _get_document_for_file(file_obj)
    if document is None:
        raise DocumentFileNotFoundError()

    user = None
    if user_id:
        user = User.objects.filter(pk=user_id).first()

    if not _user_can_view(document, user):
        raise DocumentFilePermissionError()

    return file_obj
