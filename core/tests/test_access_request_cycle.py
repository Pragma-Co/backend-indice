import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AccessStatus,
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentAccess,
    DocumentArea,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    Role,
    User,
)

PDF_BYTES = b"%PDF-1.4 confidential stress report"
JUSTIFICATION = "Preciso do relatório para o plano de inspeção da caverna 14."


class AccessRequestCycleTests(TestCase):
    def setUp(self):
        storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, storage_dir, ignore_errors=True)
        override = override_settings(DOCUMENT_STORAGE_DIR=storage_dir)
        override.enable()
        self.addCleanup(override.disable)

        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        requester_area = Area.objects.create(acronym="AER", name="Aerodinâmica")
        self.manager = self._user("manager@example.com", area)
        self.manager.role = Role.AUDITOR
        self.manager.save(update_fields=["role"])
        area.manager = self.manager
        area.save(update_fields=["manager"])
        responsible = self._user("responsible@example.com", area)
        self.requester = self._user("requester@example.com", requester_area)

        self.document = Document.objects.create(
            code="AK-2100-EST-REL-0001",
            title="Relatório da caverna 14",
            description="Análise de tensões da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="REL", name="Relatório"),
            confidentiality_level="PUBLIC",
            responsible=responsible,
            created_by=responsible,
        )
        DocumentArea.objects.create(document=self.document, area=area)
        revision = Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=responsible,
            auditor=self.manager,
            audited_at=timezone.now(),
        )
        storage_path = "documents/AK-2100-EST-REL-0001/v1/ak-2100-est-rel-0001.pdf"
        full_path = Path(storage_dir) / storage_path
        full_path.parent.mkdir(parents=True)
        full_path.write_bytes(PDF_BYTES)
        self.file = File.objects.create(
            revision=revision,
            original_name="caverna-14.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=len(PDF_BYTES),
            sha256="c" * 64,
            storage_path=storage_path,
        )

        self.requester_client = Client()
        self.requester_client.force_login(self.requester)
        self.manager_client = Client()
        self.manager_client.force_login(self.manager)

    def _user(self, email, area):
        return User.objects.create_user(
            email=email, password="secret", name=email.split("@")[0], area=area
        )

    def _request_access(self, **terms):
        body = {"justification": JUSTIFICATION, "access_type": "PERMANENT", **terms}
        return self.requester_client.post(
            reverse("document-request-access", args=[self.document.pk]),
            data=json.dumps(body),
            content_type="application/json",
        )

    def _decide(self, access_id, decision):
        return self.manager_client.post(
            reverse("manager-access-request-decision", args=[access_id]),
            data=json.dumps(
                {"decision": decision, "opinion": "Parecer técnico para esta solicitação."}
            ),
            content_type="application/json",
        )

    def _queue_ids(self):
        response = self.manager_client.get(reverse("manager-pending-access-requests"))
        return [item["id"] for item in response.json()["results"]]

    def _document_detail(self):
        return self.requester_client.get(reverse("document-detail", args=[self.document.pk]))

    def _view_file(self):
        return self.requester_client.get(reverse("document-file-view", args=[self.file.pk]))

    def test_should_keep_the_document_locked_while_the_request_is_pending(self):
        self._request_access()

        detail = self._document_detail().json()
        file_response = self._view_file()

        self.assertEqual(detail["access_status"], "PENDING")
        self.assertEqual(detail["access_request"]["status"], "PENDING")
        self.assertNotIn("description", detail)
        self.assertEqual(file_response.status_code, 403)

    def test_should_show_the_request_in_the_manager_queue_and_detail(self):
        access_id = self._request_access().json()["id"]

        queue_ids = self._queue_ids()
        detail_response = self.manager_client.get(
            reverse("manager-access-request-detail", args=[access_id])
        )

        detail = detail_response.json()
        self.assertEqual(queue_ids, [access_id])
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail["justification"], JUSTIFICATION)
        self.assertEqual(detail["requester"]["id"], self.requester.pk)
        self.assertEqual(detail["document"]["code"], self.document.code)

    def test_should_release_the_document_as_soon_as_the_manager_approves(self):
        access_id = self._request_access().json()["id"]

        decision = self._decide(access_id, "APPROVED")

        detail = self._document_detail().json()
        file_response = self._view_file()
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(detail["access_status"], "APPROVED")
        self.assertEqual(detail["access_request"]["status"], "APPROVED")
        self.assertEqual(detail["description"], "Análise de tensões da caverna 14")
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(b"".join(file_response.streaming_content), PDF_BYTES)
        self.assertEqual(self._queue_ids(), [])

    def test_should_release_a_temporary_access_with_the_requested_expiry(self):
        expires_on = timezone.localdate() + timedelta(days=7)
        access_id = self._request_access(
            access_type="TEMPORARY", expires_on=expires_on.isoformat()
        ).json()["id"]

        decision = self._decide(access_id, "APPROVED")

        detail = self._document_detail().json()
        self.assertEqual(decision.json()["expires_on"], expires_on.isoformat())
        self.assertEqual(detail["access_status"], "APPROVED")
        self.assertEqual(detail["access_request"]["expires_on"], expires_on.isoformat())
        self.assertEqual(self._view_file().status_code, 200)

    def test_should_keep_the_document_locked_when_the_manager_rejects(self):
        access_id = self._request_access().json()["id"]

        decision = self._decide(access_id, "REJECTED")

        detail = self._document_detail().json()
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(detail["access_status"], "PENDING")
        self.assertEqual(detail["access_request"]["status"], "REJECTED")
        self.assertNotIn("description", detail)
        self.assertEqual(self._view_file().status_code, 403)
        self.assertEqual(self._queue_ids(), [])

    def test_should_bring_a_new_request_back_to_the_queue_after_a_rejection(self):
        access_id = self._request_access().json()["id"]
        self._decide(access_id, "REJECTED")

        reopened = self._request_access()

        self.assertEqual(reopened.status_code, 201)
        self.assertEqual(reopened.json()["id"], access_id)
        self.assertEqual(self._queue_ids(), [access_id])
        self.assertEqual(self._view_file().status_code, 403)

    def test_should_audit_every_step_of_the_cycle(self):
        access_id = self._request_access().json()["id"]

        self._decide(access_id, "APPROVED")

        access = DocumentAccess.objects.get(pk=access_id)
        requested = AuditLog.objects.get(action=AuditAction.DOC_ACCESS_REQUESTED)
        decided = AuditLog.objects.get(entity="document_access", entity_id=access_id)
        self.assertEqual(access.status, AccessStatus.APPROVED)
        self.assertEqual(access.approver, self.manager)
        self.assertEqual(requested.user, self.requester)
        self.assertEqual(decided.user, self.manager)
        self.assertEqual(decided.record["event"], "ACCESS_APPROVED")
        self.assertEqual(decided.record["requester_id"], self.requester.pk)
