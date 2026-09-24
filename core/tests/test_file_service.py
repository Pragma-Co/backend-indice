import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    AccessStatus,
    Area,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
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


class GetDocumentFileForViewTests(TestCase):
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
