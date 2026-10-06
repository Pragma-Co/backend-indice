import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    User,
)

CHANGE_DESCRIPTION = "Corrige a furação da caverna 14 conforme ensaio"
NEW_PDF = b"%PDF-1.4 revised drawing body"


@mock.patch("core.services.document_creation_service.get_mongo_db")
@mock.patch("core.services.temp_upload_service.get_mongo_db")
class DocumentRevisionSubmissionTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        settings_override = override_settings(
            TEMP_UPLOAD_DIR=self.temp_dir, DOCUMENT_STORAGE_DIR=self.storage_dir
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.author = User.objects.create_user(
            email="author@example.com", password="secret", name="Author", area=area
        )
        self.auditor = User.objects.create_user(
            email="auditor@example.com", password="secret", name="Auditor", area=area
        )
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="DWG", name="Desenho"),
            confidentiality_level="PUBLIC",
            responsible=self.author,
            created_by=self.author,
            updated_by=self.author,
        )
        self.current_revision = self._audited_revision(1, RevisionStatus.APPROVED)

    def _audited_revision(self, version, status):
        return Revision.objects.create(
            document=self.document,
            version=version,
            status=status,
            author=self.author,
            auditor=self.auditor,
            audited_at=timezone.now(),
        )

    def _post(self, document_id=None, content=NEW_PDF, change_description=CHANGE_DESCRIPTION):
        data = {"change_description": change_description}
        if content is not None:
            data["file"] = SimpleUploadedFile("caverna-14.pdf", content)
        return self.client.post(
            reverse("document-revision-create", args=[document_id or self.document.id]), data
        )

    def test_should_create_a_pending_revision_with_the_next_version(self, *mongo):
        response = self._post()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["document_id"], self.document.id)
        self.assertEqual(body["version"], 2)
        self.assertEqual(body["status"], RevisionStatus.PENDING)
        self.assertEqual(Revision.objects.get(pk=body["id"]).status, RevisionStatus.PENDING)

    def test_should_increment_the_version_after_the_latest_revision(self, *mongo):
        Revision.objects.filter(pk=self.current_revision.pk).update(status=RevisionStatus.OBSOLETE)
        self._audited_revision(2, RevisionStatus.APPROVED)

        response = self._post()

        self.assertEqual(response.json()["version"], 3)

    def test_should_keep_the_current_revision_untouched(self, *mongo):
        self._post()

        self.current_revision.refresh_from_db()
        self.assertEqual(self.current_revision.status, RevisionStatus.APPROVED)
        self.assertEqual(Revision.objects.filter(document=self.document).count(), 2)

    def test_should_persist_the_change_description(self, *mongo):
        response = self._post(change_description=f"  {CHANGE_DESCRIPTION}  ")

        revision = Revision.objects.get(pk=response.json()["id"])
        self.assertEqual(revision.change_description, CHANGE_DESCRIPTION)
        self.assertEqual(response.json()["change_description"], CHANGE_DESCRIPTION)

    def test_should_attach_the_uploaded_file_to_the_new_revision(self, *mongo):
        response = self._post()

        stored = File.objects.get(revision_id=response.json()["id"])
        self.assertEqual(stored.original_name, "caverna-14.pdf")
        self.assertIn("/v2/", stored.storage_path)
        self.assertEqual((Path(self.storage_dir) / stored.storage_path).read_bytes(), NEW_PDF)

    def test_should_answer_404_for_a_nonexistent_document(self, *mongo):
        response = self._post(document_id=self.document.id + 1000)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "DocumentNotFound"})
        self.assertEqual(Revision.objects.count(), 1)
        self.assertEqual(list(Path(self.temp_dir).iterdir()), [])

    def test_should_answer_400_without_storing_the_file_for_a_short_description(self, *mongo):
        response = self._post(change_description="curto")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["change_description"]["code"], "too_short")
        self.assertEqual(list(Path(self.temp_dir).iterdir()), [])

    def test_should_answer_400_when_no_file_is_sent(self, *mongo):
        response = self._post(content=None)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "MissingFile"})
        self.assertEqual(Revision.objects.count(), 1)

    def test_should_answer_400_for_a_file_of_an_unsupported_type(self, *mongo):
        response = self._post(content=b"plain text pretending to be a pdf")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "InvalidFileType"})
        self.assertEqual(Revision.objects.count(), 1)

    def test_should_answer_409_for_a_file_already_registered(self, *mongo):
        self._post()

        response = self._post(change_description=f"{CHANGE_DESCRIPTION} again")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["document"]["id"], self.document.id)
        self.assertEqual(Revision.objects.count(), 2)
