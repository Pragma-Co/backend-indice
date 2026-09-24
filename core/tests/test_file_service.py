from unittest.mock import MagicMock, patch

from django.test import TestCase

from core.models.choices import AccessStatus, RevisionStatus
from core.services.documents_exceptions import DocumentFilePermissionError
from core.services.file_service import (
    DocumentFileNotFoundError,
    _get_current_revision,
    _get_document_for_file,
    _user_can_view,
    get_document_file_for_view,
)


class FileServiceTestBase(TestCase):
    def setUp(self):
        self.approved_revision = MagicMock()
        self.approved_revision.status = RevisionStatus.APPROVED

        self.pending_revision = MagicMock()
        self.pending_revision.status = RevisionStatus.PENDING

        self.document = MagicMock()
        self.document.responsible_id = 12
        self.document.revisions.all.return_value = [self.approved_revision]

        self.user = MagicMock()
        self.user.id = 99

        self.responsible_user = MagicMock()
        self.responsible_user.id = 12

        self.file_obj = MagicMock()
        self.file_obj.revision.document_id = self.document.pk
        self.file_obj.revision.document = self.document


class TestGetCurrentRevision(FileServiceTestBase):
    def test_returns_none_when_there_are_no_revisions(self):
        document = MagicMock()
        document.revisions.all.return_value = []

        self.assertIsNone(_get_current_revision(document))

    def test_returns_the_approved_revision_when_present(self):
        document = MagicMock()
        document.revisions.all.return_value = [
            self.pending_revision,
            self.approved_revision,
        ]

        self.assertIs(_get_current_revision(document), self.approved_revision)

    def test_returns_the_first_revision_when_none_is_approved(self):
        another_pending = MagicMock()
        another_pending.status = RevisionStatus.PENDING
        document = MagicMock()
        document.revisions.all.return_value = [self.pending_revision, another_pending]

        self.assertIs(_get_current_revision(document), self.pending_revision)


class TestGetDocumentForFile(FileServiceTestBase):
    def test_returns_none_when_file_has_no_revision(self):
        file_obj = MagicMock()
        file_obj.revision = None

        self.assertIsNone(_get_document_for_file(file_obj))

    @patch("core.services.file_service.Document")
    def test_queries_document_by_revision_document_id(self, DocumentMock):
        file_obj = MagicMock()
        file_obj.revision.document_id = 42

        chain = DocumentMock.objects.filter.return_value
        chain.select_related.return_value = chain
        chain.filter.return_value = chain
        chain.first.return_value = "document-42"

        result = _get_document_for_file(file_obj)

        self.assertEqual(result, "document-42")
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

        self.assertIsNone(_get_document_for_file(file_obj))


class TestUserCanView(FileServiceTestBase):
    def test_returns_false_when_user_is_none(self):
        self.assertFalse(_user_can_view(self.document, None))

    def test_returns_true_when_user_is_the_responsible(self):
        self.assertTrue(_user_can_view(self.document, self.responsible_user))

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_true_when_user_has_approved_access(self, DocumentAccessMock):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = True

        self.assertTrue(_user_can_view(self.document, self.user))

        DocumentAccessMock.objects.filter.assert_called_once_with(
            document=self.document, user=self.user, status=AccessStatus.APPROVED
        )

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_true_when_current_revision_is_approved(self, DocumentAccessMock):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = False

        self.assertTrue(_user_can_view(self.document, self.user))

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_false_when_no_access_and_revision_is_pending(self, DocumentAccessMock):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = False
        document = MagicMock()
        document.responsible_id = 12
        document.revisions.all.return_value = [self.pending_revision]

        self.assertFalse(_user_can_view(document, self.user))

    @patch("core.services.file_service.DocumentAccess")
    def test_returns_false_when_no_access_and_no_revisions(self, DocumentAccessMock):
        DocumentAccessMock.objects.filter.return_value.exists.return_value = False
        document = MagicMock()
        document.responsible_id = 12
        document.revisions.all.return_value = []

        self.assertFalse(_user_can_view(document, self.user))


class TestGetDocumentFileForView(FileServiceTestBase):
    @patch("core.services.file_service.File")
    def test_raises_when_file_does_not_exist(self, FileMock):
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = None

        with self.assertRaises(DocumentFileNotFoundError):
            get_document_file_for_view(file_id=999)

    @patch("core.services.file_service._get_document_for_file")
    @patch("core.services.file_service.File")
    def test_raises_when_document_is_not_found(self, FileMock, get_document_mock):
        FileMock.objects.select_related.return_value.filter.return_value.first.return_value = (
            MagicMock()
        )
        get_document_mock.return_value = None

        with self.assertRaises(DocumentFileNotFoundError):
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

        with self.assertRaises(DocumentFilePermissionError):
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

        self.assertIs(result, file_obj)
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

        with self.assertRaises(DocumentFilePermissionError):
            get_document_file_for_view(file_id=1, user_id=None)

        can_view_mock.assert_called_once()
        args = can_view_mock.call_args.args
        self.assertIsNone(args[1])

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

        with self.assertRaises(DocumentFilePermissionError):
            get_document_file_for_view(file_id=1, user_id=12345)

        args = can_view_mock.call_args.args
        self.assertIsNone(args[1])
