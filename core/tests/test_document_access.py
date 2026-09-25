import json
import shutil
import tempfile
from pathlib import Path

from django.test import Client, TestCase, override_settings
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
    User,
)
from core.services.documents_service import can_view_document

PDF_BYTES = b"%PDF-1.4 restricted content"


class DocumentAccessTestCase(TestCase):
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
        self.granted = User.objects.create_user(
            email="granted@example.com", password="pw", name="Granted", area=area
        )
        self.stranger = User.objects.create_user(
            email="stranger@example.com", password="pw", name="Stranger", area=area
        )
        self.manager = User.objects.create_user(
            email="manager@example.com", password="pw", name="Manager", area=area
        )
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho da caverna 14",
            description="Conjunto soldado da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="DWG", name="Desenho"),
            responsible=self.owner,
        )
        self.document.areas.add(area)
        self.revision = Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            change_description="Emissão inicial",
            author=self.owner,
            auditor=self.manager,
            audited_at=timezone.now(),
        )
        self.storage_path = "documents/AK-2100-EST-DWG-0001/v1/ak-2100-est-dwg-0001.pdf"
        full_path = Path(self.storage_dir) / self.storage_path
        full_path.parent.mkdir(parents=True)
        full_path.write_bytes(PDF_BYTES)
        self.stored_file = File.objects.create(
            revision=self.revision,
            original_name="caverna-14.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=len(PDF_BYTES),
            sha256="a" * 64,
            storage_path=self.storage_path,
        )
        DocumentAccess.objects.create(
            document=self.document,
            user=self.granted,
            status=AccessStatus.APPROVED,
            approver=self.owner,
            decided_at=timezone.now(),
        )
        self.client = Client()

    def _detail(self, user):
        return self.client.get(f"/documents/{self.document.id}", {"user_id": user.id})

    def _file(self, user=None, file_id=None, user_id=None, **headers):
        query = {}
        if user is not None:
            query["user_id"] = user.id
        if user_id is not None:
            query["user_id"] = user_id
        return self.client.get(f"/files/{file_id or self.stored_file.id}/view", query, **headers)

    def _request_access(self, user_id, justification="Preciso revisar"):
        return self.client.post(
            f"/documents/{self.document.id}/request-access",
            data=json.dumps({"user_id": user_id, "justification": justification}),
            content_type="application/json",
        )


class CanViewDocumentTests(DocumentAccessTestCase):
    def test_should_allow_the_responsible(self):
        allowed = can_view_document(self.document, self.owner)

        self.assertTrue(allowed)

    def test_should_allow_a_user_with_an_approved_grant(self):
        allowed = can_view_document(self.document, self.granted)

        self.assertTrue(allowed)

    def test_should_deny_a_user_without_a_grant_even_on_an_approved_document(self):
        allowed = can_view_document(self.document, self.stranger)

        self.assertFalse(allowed)
        self.assertFalse(can_view_document(self.document, None))

    def test_should_deny_a_pending_or_rejected_request(self):
        for status in (AccessStatus.PENDING, AccessStatus.REJECTED):
            DocumentAccess.objects.filter(user=self.stranger).delete()
            DocumentAccess.objects.create(
                document=self.document,
                user=self.stranger,
                status=status,
                requested_at=timezone.now(),
                approver=self.owner if status == AccessStatus.REJECTED else None,
                decided_at=timezone.now() if status == AccessStatus.REJECTED else None,
            )

            allowed = can_view_document(self.document, self.stranger)

            self.assertFalse(allowed, status)


class DocumentDetailAccessTests(DocumentAccessTestCase):
    def test_should_return_the_full_detail_to_the_responsible(self):
        response = self._detail(self.owner)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["access_status"], "APPROVED")
        self.assertEqual(body["description"], "Conjunto soldado da caverna 14")
        self.assertEqual(body["revision"]["change_description"], "Emissão inicial")
        stored = body["revision"]["files"][0]
        self.assertEqual(stored["original_name"], "caverna-14.pdf")
        self.assertEqual(stored["view_url"], f"/api/files/{self.stored_file.id}/view")
        self.assertNotIn("storage_path", stored)
        self.assertIsNone(body["access_request"])

    def test_should_return_the_full_detail_to_a_user_with_a_grant(self):
        response = self._detail(self.granted)

        body = response.json()
        self.assertEqual(body["access_status"], "APPROVED")
        self.assertIn("description", body)
        self.assertIn("files", body["revision"])

    def test_should_hide_the_readable_content_from_a_user_without_access(self):
        response = self._detail(self.stranger)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["access_status"], "PENDING")
        self.assertEqual(body["code"], "AK-2100-EST-DWG-0001")
        self.assertEqual(body["title"], "Desenho da caverna 14")
        self.assertEqual(body["responsible"]["id"], self.owner.id)
        self.assertEqual(body["revision"]["status"], "APPROVED")
        self.assertNotIn("description", body)
        self.assertNotIn("files", body["revision"])
        self.assertNotIn("change_description", body["revision"])
        for version in body["versions"]:
            self.assertNotIn("files", version)
            self.assertNotIn("change_description", version)
        self.assertIsNone(body["access_request"])

    def test_should_expose_the_pending_request_of_the_user(self):
        self._request_access(self.stranger.id)

        response = self._detail(self.stranger)

        request = response.json()["access_request"]
        self.assertEqual(request["status"], "PENDING")
        self.assertIsNotNone(request["created_at"])
        self.assertEqual(request["id"], DocumentAccess.objects.get(user=self.stranger).id)

    def test_should_expose_a_rejected_request(self):
        DocumentAccess.objects.create(
            document=self.document,
            user=self.stranger,
            status=AccessStatus.REJECTED,
            requested_at=timezone.now(),
            approver=self.owner,
            decided_at=timezone.now(),
        )

        response = self._detail(self.stranger)

        self.assertEqual(response.json()["access_request"]["status"], "REJECTED")
        self.assertNotIn("description", response.json())


class DocumentFileViewTests(DocumentAccessTestCase):
    def test_should_serve_the_file_to_the_responsible(self):
        response = self._file(self.owner)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('filename="caverna-14.pdf"', response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertNotIn("X-Frame-Options", response)
        self.assertEqual(b"".join(response.streaming_content), PDF_BYTES)

    def test_should_serve_the_file_to_a_user_with_a_grant(self):
        response = self._file(self.granted)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PDF_BYTES)

    def test_should_deny_a_user_without_a_grant_without_sending_any_byte(self):
        response = self._file(self.stranger)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "AccessDenied"})
        self.assertNotIn(PDF_BYTES, response.content)

    @override_settings(AUDIT_TRUST_FORWARDED_FOR=True)
    def test_should_record_the_denied_attempt_in_the_audit_trail(self):
        self._file(self.stranger, HTTP_X_FORWARDED_FOR="203.0.113.7")

        entry = AuditLog.objects.get()
        self.assertEqual(entry.user, self.stranger)
        self.assertEqual(entry.action, AuditAction.READ)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, self.document.id)
        self.assertEqual(entry.ip_address, "203.0.113.7")
        self.assertEqual(entry.record["event"], "DOCUMENT_ACCESS_DENIED")
        self.assertEqual(entry.record["outcome"], "denied")

    def test_should_not_record_anything_when_the_file_is_served(self):
        self._file(self.owner)

        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_require_a_user(self):
        response = self._file()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "MissingUser"})

    def test_should_answer_404_in_json_for_an_unknown_user_or_file(self):
        unknown_user = self._file(user_id=999999)
        unknown_file = self._file(self.owner, file_id=999999)

        self.assertEqual(unknown_user.status_code, 404)
        self.assertEqual(unknown_user.json(), {"error": "UserNotFound"})
        self.assertEqual(unknown_file.status_code, 404)
        self.assertEqual(unknown_file.json(), {"error": "FileNotFound"})

    def test_should_answer_404_when_the_file_is_missing_from_storage(self):
        (Path(self.storage_dir) / self.storage_path).unlink()

        response = self._file(self.owner)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "FileNotFound"})

    def test_should_answer_404_when_the_document_type_is_inactive(self):
        self.document.document_type.active = False
        self.document.document_type.save()

        response = self._file(self.owner)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "FileNotFound"})

    def test_should_reject_other_methods(self):
        response = self.client.post(f"/files/{self.stored_file.id}/view")

        self.assertEqual(response.status_code, 405)


class RequestAccessTests(DocumentAccessTestCase):
    def test_should_create_a_pending_request_for_a_user_without_access(self):
        response = self._request_access(self.stranger.id)

        body = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["status"], "PENDING")
        self.assertTrue(body["created"])
        self.assertEqual(DocumentAccess.objects.filter(user=self.stranger).count(), 1)

    def test_should_not_duplicate_a_pending_request(self):
        first = self._request_access(self.stranger.id)

        second = self._request_access(self.stranger.id)

        self.assertEqual(second.status_code, 201)
        self.assertFalse(second.json()["created"])
        self.assertEqual(second.json()["id"], first.json()["id"])

    def test_should_record_the_access_request_in_the_audit_trail(self):
        response = self._request_access(self.stranger.id, "Preciso consultar o desenho")

        entry = AuditLog.objects.get(action=AuditAction.DOC_ACCESS_REQUESTED)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.user, self.stranger)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, self.document.id)
        self.assertEqual(entry.record["document_code"], self.document.code)
        self.assertEqual(entry.record["justification"], "Preciso consultar o desenho")
        self.assertFalse(entry.record["already_requested"])

    def test_should_answer_409_for_the_responsible(self):
        response = self._request_access(self.owner.id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "AlreadyHasAccess"})
        self.assertFalse(DocumentAccess.objects.filter(user=self.owner).exists())

    def test_should_answer_409_for_a_user_who_already_has_a_grant(self):
        response = self._request_access(self.granted.id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "AlreadyHasAccess"})

    def test_should_keep_the_user_errors(self):
        missing = self._request_access(None)
        unknown = self._request_access(999999)

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json(), {"error": "MissingUser"})
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json(), {"error": "UserNotFound"})
