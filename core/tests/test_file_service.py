from unittest.mock import MagicMock, patch

import pytest

from core.models.choices import AccessStatus, RevisionStatus
from core.services.documents_exceptions import DocumentFilePermissionError
from core.services.file_service import (
    DocumentFileNotFoundError,
    _get_current_revision,
    _get_document_for_file,
    _user_can_view,
    get_document_file_for_view,
)


@pytest.fixture
def approved_revision():
    rev = MagicMock()
    rev.status = RevisionStatus.APPROVED
    return rev


@pytest.fixture
def pending_revision():
    rev = MagicMock()
    rev.status = RevisionStatus.PENDING
    return rev


@pytest.fixture
def document(approved_revision):
    doc = MagicMock()
    doc.responsible_id = 12
    doc.revisions.all.return_value = [approved_revision]
    return doc


@pytest.fixture
def user():
    u = MagicMock()
    u.id = 99
    return u


@pytest.fixture
def responsible_user():
    u = MagicMock()
    u.id = 12
    return u


@pytest.fixture
def file_obj(document):
    f = MagicMock()
    f.revision.document_id = document.pk
    f.revision.document = document
    return f


class TestGetCurrentRevision:
    def test_returns_none_when_there_are_no_revisions(self):
        document = MagicMock()
        document.revisions.all.return_value = []

        assert _get_current_revision(document) is None

    def test_returns_the_approved_revision_when_present(self, approved_revision, pending_revision):
        document = MagicMock()
        document.revisions.all.return_value = [pending_revision, approved_revision]

        assert _get_current_revision(document) is approved_revision

    def test_returns_the_first_revision_when_none_is_approved(self, pending_revision):
        another_pending = MagicMock()
        another_pending.status = RevisionStatus.PENDING
        document = MagicMock()
        document.revisions.all.return_value = [pending_revision, another_pending]

        assert _get_current_revision(document) is pending_revision


class TestGetDocumentForFile:
    def test_returns_none_when_file_has_no_revision(self):
        file_obj = MagicMock()
        file_obj.revision = None

        assert _get_document_for_file(file_obj) is None

    @patch("core.services.file_service.Document")
    def test_queries_document_by_revision_document_id(self, DocumentMock):
        file_obj = MagicMock()
        file_obj.revision.document_id = 42

        chain = DocumentMock.objects.filter.return_value
        chain.select_related.return_value = chain
        chain.filter.return_value = chain
        chain.first.return_value = "document-42"

        result = _get_document_for_file(file_obj)

        assert result == "document-42"
        DocumentMock.objects.filter.assert_called_once_with(document_type__active=True)
        chain.filter.assert_called_once_with(pk=42)

    @patch("core.services.file_service.Document")
    def test_returns_none_when_document_does_not_exist(self, DocumentMock):
        file_obj = MagicMock()
        file_obj.revision.document_id = 42

        chain = DocumentMock.objects.filter.return_value
        chain.select_related.return_value = chain
        chain.filter.return_value = chain
        chain.first.return_value = None

        assert _get_document_for_file(file_obj) is None


class TestUserCanView:
    def test_returns_false_when_user_is_none(self, document):
        assert _user_can_view(document, None) is False

    def test_returns_true_when_user_is_the_responsible(self, document, responsible_user):
        assert _user_can_view(document, responsible_user) is True

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_true_when_user_has_approved_access(self, DocumentAccessMock, document, user):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = True

        assert _user_can_view(document, user) is True

        DocumentAccessMock.objects.filter.assert_called_once_with(
            document=document, user=user, status=AccessStatus.APPROVED
        )

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_true_when_current_revision_is_approved(
        self, DocumentAccessMock, document, user, approved_revision
    ):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = False

        assert _user_can_view(document, user) is True

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_false_when_no_access_and_revision_is_pending(
        self, DocumentAccessMock, user, pending_revision
    ):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = False
        document = MagicMock()
        document.responsible_id = 12
        document.revisions.all.return_value = [pending_revision]

        assert _user_can_view(document, user) is False

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_false_when_no_access_and_no_revisions(self, DocumentAccessMock, user):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = False
        document = MagicMock()
        document.responsible_id = 12
        document.revisions.all.return_value = []

        assert _user_can_view(document, user) is False


class TestGetDocumentFileForView:
    @patch("core.services.file_service.File")
    def test_raises_when_file_does_not_exist(self, FileMock):
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = None

        with pytest.raises(DocumentFileNotFoundError):
            get_document_file_for_view(file_id=999)

    @patch("core.services.file_service._get_document_for_file")
    @patch("core.services.file_service.File")
    def test_raises_when_document_is_not_found(self, FileMock, get_document_mock):
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = (
            MagicMock()
        )
        get_document_mock.return_value = None

        with pytest.raises(DocumentFileNotFoundError):
            get_document_file_for_view(file_id=1)

    @patch("core.services.file_service._user_can_view")
    @patch("core.services.file_service._get_document_for_file")
    @patch("core.services.file_service.File")
    def test_raises_permission_error_when_user_cannot_view(
        self, FileMock, get_document_mock, can_view_mock
    ):
        file_obj = MagicMock()
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = (
            file_obj
        )
        get_document_mock.return_value = MagicMock()
        can_view_mock.return_value = False

        with pytest.raises(DocumentFilePermissionError):
            get_document_file_for_view(file_id=1, user_id=99)

    @patch("core.services.file_service.User")
    @patch("core.services.file_service._user_can_view")
    @patch("core.services.file_service._get_document_for_file")
    @patch("core.services.file_service.File")
    def test_returns_file_when_user_can_view(
        self, FileMock, get_document_mock, can_view_mock, UserMock
    ):
        file_obj = MagicMock()
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = (
            file_obj
        )
        document = MagicMock()
        get_document_mock.return_value = document
        can_view_mock.return_value = True
        user = MagicMock()
        UserMock.objects.filter.return_value.first.return_value = user

        result = get_document_file_for_view(file_id=1, user_id=99)

        assert result is file_obj
        UserMock.objects.filter.assert_called_once_with(pk=99)
        can_view_mock.assert_called_once_with(document, user)

    @patch("core.services.file_service._user_can_view")
    @patch("core.services.file_service._get_document_for_file")
    @patch("core.services.file_service.File")
    def test_does_not_query_user_when_user_id_is_none(
        self, FileMock, get_document_mock, can_view_mock
    ):
        file_obj = MagicMock()
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = (
            file_obj
        )
        get_document_mock.return_value = MagicMock()
        can_view_mock.return_value = False

        with pytest.raises(DocumentFilePermissionError):
            get_document_file_for_view(file_id=1, user_id=None)

        can_view_mock.assert_called_once()
        _, args = can_view_mock.call_args
        assert args[1] is None

    @patch("core.services.file_service.User")
    @patch("core.services.file_service._user_can_view")
    @patch("core.services.file_service._get_document_for_file")
    @patch("core.services.file_service.File")
    def test_returns_none_user_when_user_id_does_not_exist(
        self, FileMock, get_document_mock, can_view_mock, UserMock
    ):
        file_obj = MagicMock()
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = (
            file_obj
        )
        get_document_mock.return_value = MagicMock()
        UserMock.objects.filter.return_value.first.return_value = None
        can_view_mock.return_value = False

        with pytest.raises(DocumentFilePermissionError):
            get_document_file_for_view(file_id=1, user_id=12345)

        _, args = can_view_mock.call_args
        assert args[1] is None
