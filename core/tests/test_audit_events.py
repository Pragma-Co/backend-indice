import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, RequestFactory, TestCase, override_settings

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentType,
    File,
    Project,
    Revision,
    User,
)
from core.views.documents_view import create_document_view

LOGGER_NAME = "core.services.audit_service"
PDF_HEADER = b"%PDF-1.4 fake pdf body"
PDF_BYTES = b"%PDF-1.4 test document body"
TEMP_FILE_ID = "11111111-2222-4333-8444-555555555555"
SECOND_TEMP_FILE_ID = "22222222-2222-4333-8444-555555555555"


class UploadAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        settings_override = override_settings(
            TEMP_UPLOAD_DIR=self.temp_dir, MAX_UPLOAD_SIZE_BYTES=1024 * 1024
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        area = Area.objects.create(acronym="AUD", name="Auditoria")
        self.user = User.objects.create_user(
            email="audit@example.com", password="secret", name="Auditora", area=area
        )

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_should_record_upload_success_for_the_logged_in_user(self, mongo):
        self.client.force_login(self.user)
        uploaded = SimpleUploadedFile("relatorio.pdf", PDF_HEADER)

        response = self.client.post("/documents/upload", {"file": uploaded})

        entry = AuditLog.objects.get()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, AuditAction.DOC_UPLOAD_SUCCESS)
        self.assertEqual(entry.entity, "temp_upload")
        self.assertEqual(entry.record["temp_file_id"], response.json()["temp_file_id"])
        self.assertEqual(entry.record["original_name"], "relatorio.pdf")
        self.assertEqual(entry.record["actor"]["name"], "Auditora")
        self.assertEqual(entry.ip_address, "127.0.0.1")

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_should_record_the_declared_user_when_nobody_is_logged_in(self, mongo):
        uploaded = SimpleUploadedFile("relatorio.pdf", PDF_HEADER)

        self.client.post("/documents/upload", {"file": uploaded, "user_id": str(self.user.id)})

        entry = AuditLog.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertFalse(entry.record["actor"]["authenticated"])

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_should_not_record_anything_when_the_upload_is_rejected(self, mongo):
        uploaded = SimpleUploadedFile("fake.pdf", b"this is a plain text file")

        response = self.client.post("/documents/upload", {"file": uploaded})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AuditLog.objects.count(), 0)

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_should_still_answer_201_when_the_audit_write_fails(self, mongo):
        uploaded = SimpleUploadedFile("relatorio.pdf", PDF_HEADER)

        with (
            mock.patch.object(AuditLog.objects, "create", side_effect=DatabaseError("boom")),
            self.assertLogs(LOGGER_NAME, level="ERROR"),
        ):
            response = self.client.post("/documents/upload", {"file": uploaded})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AuditLog.objects.count(), 0)


class UploadDuplicateAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        settings_override = override_settings(
            TEMP_UPLOAD_DIR=self.temp_dir, MAX_UPLOAD_SIZE_BYTES=1024 * 1024
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        area = Area.objects.create(acronym="AUD", name="Auditoria")
        self.user = User.objects.create_user(
            email="audit@example.com", password="secret", name="Auditora", area=area
        )
        project = Project.objects.create(code="PRJ-A", name="Projeto Audit")
        discipline = Discipline.objects.create(code="DISA", name="Disciplina Audit")
        document_type = DocumentType.objects.create(code="DTA", name="Tipo Audit")
        self.document = Document.objects.create(
            code="RA-0700",
            title="Documento Existente",
            project=project,
            discipline=discipline,
            document_type=document_type,
            responsible=self.user,
        )
        revision = Revision.objects.create(
            document=self.document, version=1, status="PENDING", author=self.user
        )
        File.objects.create(
            revision=revision,
            original_name="original.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=len(PDF_HEADER),
            sha256=hashlib.sha256(PDF_HEADER).hexdigest(),
            storage_path="/fake/path/original.pdf",
        )

    def test_should_record_the_duplicate_attempt_against_the_existing_document(self):
        self.client.force_login(self.user)
        uploaded = SimpleUploadedFile("copia.pdf", PDF_HEADER)

        response = self.client.post("/documents/upload", {"file": uploaded})

        entry = AuditLog.objects.get()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, AuditAction.DOC_UPLOAD_DUPLICATE)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, self.document.id)
        self.assertEqual(entry.record["stage"], "upload")
        self.assertEqual(entry.record["document_code"], "RA-0700")
        self.assertEqual(entry.record["original_name"], "copia.pdf")
        self.assertEqual(entry.record["sha256"], hashlib.sha256(PDF_HEADER).hexdigest())


@mock.patch("core.services.document_creation_service.get_mongo_db")
class SubmissionAuditTests(TestCase):
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

        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=self.area
        )
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.project.disciplines.add(self.discipline)
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")

    def _temp_file(self, temp_file_id=TEMP_FILE_ID, content=PDF_BYTES):
        path = Path(self.temp_dir) / f"{temp_file_id}.pdf"
        path.write_bytes(content)
        return path

    def _payload(self, **overrides):
        payload = {
            "temp_file_id": TEMP_FILE_ID,
            "title": "Desenho da caverna 14",
            "description": "Conjunto soldado",
            "project_id": self.project.id,
            "discipline_id": self.discipline.id,
            "document_type": self.document_type.id,
            "confidentiality": "CONFIDENTIAL",
            "responsible_id": self.user.id,
            "areas": ["EST"],
        }
        payload.update(overrides)
        return payload

    def _post(self, payload, user=None):
        request = RequestFactory().post(
            "/documents", data=json.dumps(payload), content_type="application/json"
        )
        request.user = user if user is not None else AnonymousUser()
        return create_document_view(request)

    def test_should_record_the_submission_with_the_document_and_the_author(self, mongo):
        self._temp_file()

        response = self._post(self._payload(), self.user)

        document = Document.objects.get()
        entry = AuditLog.objects.get()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, AuditAction.DOC_SUBMIT_SUCCESS)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, document.id)
        self.assertEqual(entry.record["document_code"], document.code)
        self.assertEqual(entry.record["temp_file_id"], TEMP_FILE_ID)

    def test_should_not_record_anything_when_the_submission_is_invalid(self, mongo):
        self._temp_file()

        response = self._post(self._payload(title=""), self.user)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_record_the_duplicate_attempt_made_at_submission(self, mongo):
        self._temp_file()
        self._post(self._payload(), self.user)
        self._temp_file(temp_file_id=SECOND_TEMP_FILE_ID)

        response = self._post(self._payload(temp_file_id=SECOND_TEMP_FILE_ID), self.user)

        document = Document.objects.get()
        entry = AuditLog.objects.get(action=AuditAction.DOC_UPLOAD_DUPLICATE)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(entry.entity_id, document.id)
        self.assertEqual(entry.record["stage"], "submit")
        self.assertEqual(entry.record["temp_file_id"], SECOND_TEMP_FILE_ID)

    def test_should_still_answer_201_when_the_audit_write_fails(self, mongo):
        self._temp_file()

        with (
            mock.patch.object(AuditLog.objects, "create", side_effect=DatabaseError("boom")),
            self.assertLogs(LOGGER_NAME, level="ERROR"),
        ):
            response = self._post(self._payload(), self.user)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(AuditLog.objects.count(), 0)
