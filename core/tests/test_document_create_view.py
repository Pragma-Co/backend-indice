import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentType,
    Project,
    User,
)
from core.services.document_exceptions import (
    DocumentCodeCollisionError,
    DocumentStorageError,
)

PDF_BYTES = b"%PDF-1.4 view test body"
TEMP_FILE_ID = "aaaaaaaa-2222-4333-8444-555555555555"


@mock.patch("core.services.document_creation_service.get_mongo_db")
class CreateDocumentViewTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        override = override_settings(
            TEMP_UPLOAD_DIR=self.temp_dir, DOCUMENT_STORAGE_DIR=self.storage_dir
        )
        override.enable()
        self.addCleanup(override.disable)

        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=self.area
        )
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.project.disciplines.add(self.discipline)
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.url = reverse("document-list")

    def _temp_file(self, extension="pdf", content=PDF_BYTES):
        path = Path(self.temp_dir) / f"{TEMP_FILE_ID}.{extension}"
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
            "confidentiality": "PUBLIC",
            "responsible_id": self.user.id,
            "areas": ["EST"],
        }
        payload.update(overrides)
        return payload

    def _post(self, payload, client=None, **extra):
        return (client or self.client).post(
            self.url, data=json.dumps(payload), content_type="application/json", **extra
        )

    def test_should_create_the_document_and_answer_201_with_the_consolidated_data(self, mongo):
        self._temp_file()
        mongo.return_value.__getitem__.return_value.find_one.return_value = {
            "original_name": "caverna-14.pdf",
            "inferred_type": "application/pdf",
        }

        response = self._post(self._payload())

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["code"], "AK-2100-EST-DWG-0001")
        self.assertEqual(body["title"], "Desenho da caverna 14")
        self.assertEqual(body["project"]["code"], "AK-2100")
        self.assertEqual(body["discipline"]["code"], "EST")
        self.assertEqual(body["document_type"]["code"], "DWG")
        self.assertEqual(body["confidentiality"], "PUBLIC")
        self.assertEqual(body["responsible"]["email"], "ana@example.com")
        self.assertEqual(body["areas"], [{"acronym": "EST", "name": "Engenharia Estrutural"}])
        self.assertEqual(body["revision"]["label"], "REV01")
        self.assertEqual(body["revision"]["status"], "PENDING")
        self.assertIsNotNone(body["revision"]["issue_date"])
        self.assertEqual(body["file"]["original_name"], "caverna-14.pdf")
        self.assertIn("created_at", body)
        self.assertEqual(Document.objects.count(), 1)

    def test_should_register_images_accepted_by_the_upload(self, mongo):
        images = {"jpeg": b"\xff\xd8\xff fake jpeg body", "png": b"\x89PNG\r\n\x1a\n fake png body"}

        for extension, content in images.items():
            with self.subTest(extension=extension):
                self._temp_file(extension=extension, content=content)

                response = self._post(self._payload(title=f"Imagem {extension}"))

                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()["file"]["extension"], extension)
                self.assertTrue(response.json()["file"]["storage_path"].endswith(f".{extension}"))

    def test_should_answer_400_with_a_code_and_message_per_invalid_field(self, mongo):
        payload = {}

        response = self._post(payload)

        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertEqual(errors["title"], {"code": "required", "message": "Title is required."})
        self.assertEqual(errors["areas"]["code"], "invalid")
        self.assertEqual(errors["temp_file_id"]["code"], "required")
        for error in errors.values():
            self.assertEqual(set(error), {"code", "message"})
        self.assertEqual(Document.objects.count(), 0)

    def test_should_answer_400_for_invalid_json(self, mongo):
        body = "{not json"

        response = self.client.post(self.url, data=body, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Request body must be valid JSON."})

    def test_should_answer_404_when_the_uploaded_file_is_gone(self, mongo):

        response = self._post(self._payload())

        self.assertEqual(response.status_code, 404)
        error = response.json()["errors"]["temp_file_id"]
        self.assertEqual(error["code"], "not_found")
        self.assertTrue(error["message"])
        self.assertEqual(Document.objects.count(), 0)

    def test_should_answer_409_when_the_file_is_already_registered(self, mongo):
        self._temp_file()
        self._post(self._payload())
        self._temp_file()

        response = self._post(self._payload())

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["document"]["code"], "AK-2100-EST-DWG-0001")
        self.assertEqual(Document.objects.count(), 1)

    def test_should_answer_500_without_internal_details_when_storage_fails(self, mongo):
        self._temp_file()

        with mock.patch(
            "core.views.documents_view.create_document",
            side_effect=DocumentStorageError(),
        ):
            response = self._post(self._payload())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "Failed to store the file. Please try again."})

    def test_should_answer_503_when_no_unique_code_could_be_generated(self, mongo):
        self._temp_file()

        with mock.patch(
            "core.views.documents_view.create_document",
            side_effect=DocumentCodeCollisionError("AK-2100-EST-DWG"),
        ):
            response = self._post(self._payload())

        self.assertEqual(response.status_code, 503)

    def test_should_hide_internal_details_on_unexpected_errors(self, mongo):
        internal_detail = 'connection to server at "postgres" (10.0.0.5) failed'

        with (
            mock.patch(
                "core.views.documents_view.create_document",
                side_effect=RuntimeError(internal_detail),
            ),
            self.assertLogs("core.views.documents_view", level="ERROR") as logs,
        ):
            response = self._post(self._payload())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})
        self.assertNotIn("postgres", response.content.decode())
        self.assertIn(internal_detail, "\n".join(logs.output))

    def test_should_keep_get_working_and_reject_other_methods(self, mongo):
        client = Client(enforce_csrf_checks=True)

        get_response = client.get(self.url)
        put_response = client.put(self.url)

        self.assertEqual(get_response.status_code, 200)
        self.assertIn("results", get_response.json())
        self.assertEqual(put_response.status_code, 405)
        self.assertEqual(put_response["Allow"], "GET, POST")

    def test_should_accept_post_with_csrf_checks_enforced(self, mongo):
        self._temp_file()
        client = Client(enforce_csrf_checks=True)

        response = self._post(self._payload(), client=client)

        self.assertEqual(response.status_code, 201)

    @override_settings(AUDIT_TRUST_FORWARDED_FOR=True)
    def test_should_record_the_document_created_event_after_publishing(self, mongo):
        self._temp_file()

        response = self._post(
            self._payload(),
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
            HTTP_USER_AGENT="Mozilla/5.0 (test)",
        )

        self.assertEqual(response.status_code, 201)
        entry = AuditLog.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, AuditAction.DOC_SUBMIT_SUCCESS)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, response.json()["id"])
        self.assertEqual(entry.ip_address, "203.0.113.7")
        self.assertEqual(entry.record["document_code"], response.json()["code"])
        self.assertEqual(entry.record["version"], 1)
        self.assertEqual(entry.record["revision"], "REV01")
        self.assertEqual(entry.record["user_agent"], "Mozilla/5.0 (test)")

    def test_should_still_answer_201_when_the_audit_log_cannot_be_written(self, mongo):
        self._temp_file()

        with (
            mock.patch.object(AuditLog.objects, "create", side_effect=RuntimeError("db down")),
            self.assertLogs("core.services.audit_service", level="ERROR"),
        ):
            response = self._post(self._payload())

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_not_record_an_event_when_the_document_is_rejected(self, mongo):
        response = self._post({})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AuditLog.objects.count(), 0)
