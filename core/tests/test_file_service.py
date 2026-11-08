import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    AccessStatus,
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    Role,
    User,
)
from core.services.documents_exceptions import (
    AccessDeniedError,
    DocumentFileNotFoundError,
    MissingUserError,
    UserNotFoundError,
)
from core.services.file_service import get_document_file_for_view

PDF_BYTES = b"%PDF-1.4 file service"


class StoredFileFixtureMixin:
    def setUp(self):
        self.storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        override = override_settings(DOCUMENT_STORAGE_DIR=self.storage_dir)
        override.enable()
        self.addCleanup(override.disable)

        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.owner = User.objects.create_user(
            email="owner@example.com", password="pw", name="Owner", area=area
        )
        self.reader = User.objects.create_user(
            email="reader@example.com", password="pw", name="Reader", area=area
        )
        self.stranger = User.objects.create_user(
            email="stranger@example.com", password="pw", name="Stranger", area=area
        )
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="DWG", name="Desenho"),
            responsible=self.owner,
            created_by=self.owner,
            updated_by=self.owner,
        )
        revision = Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.owner,
            auditor=self.reader,
            audited_at=timezone.now(),
        )
        self.storage_path = "documents/AK-2100-EST-DWG-0001/v1/ak-2100-est-dwg-0001.pdf"
        full_path = Path(self.storage_dir) / self.storage_path
        full_path.parent.mkdir(parents=True)
        full_path.write_bytes(PDF_BYTES)
        self.stored_file = File.objects.create(
            revision=revision,
            original_name="desenho.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=len(PDF_BYTES),
            sha256="b" * 64,
            storage_path=self.storage_path,
        )
        DocumentAccess.objects.create(
            document=self.document,
            user=self.reader,
            status=AccessStatus.APPROVED,
            approver=self.owner,
            decided_at=timezone.now(),
        )


class GetDocumentFileForViewTests(StoredFileFixtureMixin, TestCase):
    def test_should_return_the_file_and_its_path_to_the_responsible(self):
        file_obj, path = get_document_file_for_view(self.stored_file.id, self.owner.id)

        self.assertEqual(file_obj, self.stored_file)
        self.assertEqual(path.read_bytes(), PDF_BYTES)

    def test_should_return_the_file_to_a_user_with_an_approved_grant(self):
        file_obj, _ = get_document_file_for_view(self.stored_file.id, self.reader.id)

        self.assertEqual(file_obj, self.stored_file)

    def test_should_deny_a_user_without_a_grant_even_when_the_revision_is_approved(self):
        with self.assertRaises(AccessDeniedError) as context:
            get_document_file_for_view(self.stored_file.id, self.stranger.id)

        document, user = context.exception.args
        self.assertEqual(document, self.document)
        self.assertEqual(user, self.stranger)

    def test_should_require_a_user(self):
        with self.assertRaises(MissingUserError):
            get_document_file_for_view(self.stored_file.id, None)

    def test_should_reject_an_unknown_user(self):
        with self.assertRaises(UserNotFoundError):
            get_document_file_for_view(self.stored_file.id, 999999)

    def test_should_raise_for_an_unknown_file(self):
        with self.assertRaises(DocumentFileNotFoundError):
            get_document_file_for_view(999999, self.owner.id)

    def test_should_raise_when_the_bytes_are_missing_from_storage(self):
        (Path(self.storage_dir) / self.storage_path).unlink()

        with self.assertRaises(DocumentFileNotFoundError):
            get_document_file_for_view(self.stored_file.id, self.owner.id)


class ReviewerFileAccessTests(StoredFileFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        area = Area.objects.get(acronym="EST")
        self.reviewer = User.objects.create_user(
            email="reviewer@example.com",
            password="pw",
            name="Reviewer",
            area=area,
            role=Role.AUDITOR,
        )
        pending_revision = Revision.objects.create(
            document=self.document,
            version=2,
            status=RevisionStatus.PENDING,
            author=self.owner,
        )
        pending_path = "documents/AK-2100-EST-DWG-0001/v2/ak-2100-est-dwg-0001.pdf"
        full_path = Path(self.storage_dir) / pending_path
        full_path.parent.mkdir(parents=True)
        full_path.write_bytes(PDF_BYTES)
        self.pending_file = File.objects.create(
            revision=pending_revision,
            original_name="desenho-rev02.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=len(PDF_BYTES),
            sha256="c" * 64,
            storage_path=pending_path,
        )

    def test_should_return_the_file_of_a_pending_revision_to_a_reviewer(self):
        file_obj, path = get_document_file_for_view(self.pending_file.id, self.reviewer.id)

        self.assertEqual(file_obj, self.pending_file)
        self.assertEqual(path.read_bytes(), PDF_BYTES)

    def test_should_deny_the_file_of_a_pending_revision_to_a_user_who_is_not_a_reviewer(self):
        with self.assertRaises(AccessDeniedError):
            get_document_file_for_view(self.pending_file.id, self.stranger.id)

    def test_should_deny_a_reviewer_without_a_grant_once_the_revision_is_no_longer_pending(self):
        revision = self.pending_file.revision
        revision.status = RevisionStatus.REJECTED
        revision.auditor = self.reviewer
        revision.audited_at = timezone.now()
        revision.save(update_fields=["status", "auditor", "audited_at"])

        with self.assertRaises(AccessDeniedError):
            get_document_file_for_view(self.pending_file.id, self.reviewer.id)

    def test_should_deny_a_reviewer_without_a_grant_on_an_already_approved_revision(self):
        with self.assertRaises(AccessDeniedError):
            get_document_file_for_view(self.stored_file.id, self.reviewer.id)

    def test_should_deny_an_inactive_reviewer(self):
        self.reviewer.is_active = False
        self.reviewer.save(update_fields=["is_active"])

        with self.assertRaises(AccessDeniedError):
            get_document_file_for_view(self.pending_file.id, self.reviewer.id)


class DocumentFileViewCaptureProtectionTests(StoredFileFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)
        self.url = f"/api/files/{self.stored_file.id}/view"

    def test_should_serve_the_file_to_fetch_requests_with_hardening_headers(self):
        response = self.client.get(self.url, HTTP_SEC_FETCH_DEST="empty")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", response["Cache-Control"])

    def test_should_refuse_and_log_when_the_file_is_opened_as_a_document(self):
        response = self.client.get(self.url, HTTP_SEC_FETCH_DEST="document")

        self.assertEqual(response.status_code, 403)
        entry = AuditLog.objects.get(action=AuditAction.DOC_CAPTURE_ATTEMPT)
        self.assertEqual(entry.record["event"], "DIRECT_FILE_NAVIGATION")
        self.assertEqual(entry.user, self.owner)


class DocumentSecurityEventViewTests(StoredFileFixtureMixin, TestCase):
    def post(self, payload):
        return self.client.post(
            f"/api/documents/{self.document.id}/security-events",
            payload,
            content_type="application/json",
        )

    def test_should_log_a_known_event_for_a_viewer(self):
        self.client.force_login(self.reader)

        response = self.post({"event": "PRINT_SCREEN_KEY", "file_id": self.stored_file.id})

        self.assertEqual(response.status_code, 201)
        entry = AuditLog.objects.get(action=AuditAction.DOC_CAPTURE_ATTEMPT)
        self.assertEqual(entry.record["event"], "PRINT_SCREEN_KEY")
        self.assertEqual(entry.record["severity"], "HIGH")
        self.assertEqual(entry.user, self.reader)

    def test_should_log_focus_loss_as_info_severity(self):
        self.client.force_login(self.reader)

        self.post({"event": "FOCUS_LOST"})

        entry = AuditLog.objects.get(action=AuditAction.DOC_CAPTURE_ATTEMPT)
        self.assertEqual(entry.record["severity"], "INFO")

    def test_should_reject_unknown_events(self):
        self.client.force_login(self.reader)

        self.assertEqual(self.post({"event": "ANYTHING"}).status_code, 400)

    def test_should_not_log_for_users_without_access(self):
        self.client.force_login(self.stranger)

        self.assertEqual(self.post({"event": "PRINT_SCREEN_KEY"}).status_code, 404)
        self.assertFalse(AuditLog.objects.filter(action=AuditAction.DOC_CAPTURE_ATTEMPT).exists())
