from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentType,
    Project,
    Revision,
    User,
)
from core.services import audit_service
from core.services.audit_service import (
    USER_AGENT_MAX_LENGTH,
    client_ip,
    client_user_agent,
    record_document_created,
)

LOGGER_NAME = "core.services.audit_service"


class AuditServiceTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=self.area
        )
        self.other_user = User.objects.create_user(
            email="bia@example.com", password="secret", name="Bia", area=self.area
        )

    def _request(self, user=None, data=None, **extra):
        request = self.factory.post("/documents/upload", data=data or {}, **extra)
        request.user = user if user is not None else AnonymousUser()
        return request

    def test_should_record_event_with_the_authenticated_user_id_and_name(self):
        request = self._request(self.user)

        audit_service.log_event(
            request,
            AuditAction.DOC_UPLOAD_SUCCESS,
            audit_service.ENTITY_TEMP_UPLOAD,
            details={"temp_file_id": "abc"},
        )

        entry = AuditLog.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, AuditAction.DOC_UPLOAD_SUCCESS)
        self.assertEqual(entry.entity, "temp_upload")
        self.assertIsNone(entry.entity_id)
        self.assertEqual(entry.record["temp_file_id"], "abc")
        self.assertEqual(
            entry.record["actor"],
            {"id": self.user.id, "name": "Ana", "authenticated": True},
        )

    def test_should_keep_the_user_name_in_the_record_after_the_user_is_deleted(self):
        request = self._request(self.user)
        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        self.user.delete()
        entry = AuditLog.objects.get()

        self.assertIsNone(entry.user)
        self.assertEqual(entry.record["actor"]["name"], "Ana")

    def test_should_store_occurred_at_in_utc(self):
        request = self._request(self.user)

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.occurred_at.utcoffset(), timedelta(0))
        self.assertLess(abs(timezone.now() - entry.occurred_at), timedelta(minutes=1))

    def test_should_record_event_without_user_when_request_is_anonymous(self):
        request = self._request()

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertIsNone(entry.user)
        self.assertNotIn("actor", entry.record)

    def test_should_use_the_declared_user_id_and_mark_it_as_not_authenticated(self):
        request = self._request(data={"user_id": str(self.user.id)})

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertFalse(entry.record["actor"]["authenticated"])

    def test_should_read_the_declared_user_id_from_the_json_body(self):
        request = self._request()

        audit_service.log_event(
            request,
            AuditAction.DOC_DOWNLOAD,
            "document",
            3,
            body={"user_id": self.user.id},
        )

        entry = AuditLog.objects.get()
        self.assertEqual(entry.user, self.user)

    def test_should_prefer_the_authenticated_user_over_a_declared_user_id(self):
        request = self._request(self.user, data={"user_id": str(self.other_user.id)})

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.user, self.user)
        self.assertTrue(entry.record["actor"]["authenticated"])

    def test_should_ignore_declared_ids_that_do_not_match_an_active_user(self):
        inactive = User.objects.create_user(
            email="off@example.com", password="secret", name="Off", area=self.area
        )
        inactive.is_active = False
        inactive.save()

        for declared in ("9999", "abc", "", str(inactive.id), "true"):
            with self.subTest(declared=declared):
                request = self._request(data={"user_id": declared})

                audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

                entry = AuditLog.objects.latest("id")
                self.assertIsNone(entry.user)
                self.assertNotIn("actor", entry.record)

    def test_should_record_the_remote_address_of_the_request(self):
        request = self._request(self.user, REMOTE_ADDR="203.0.113.7")

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.ip_address, "203.0.113.7")

    def test_should_ignore_forwarded_for_unless_it_is_trusted(self):
        request = self._request(
            self.user, REMOTE_ADDR="172.18.0.1", HTTP_X_FORWARDED_FOR="198.51.100.9"
        )

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.ip_address, "172.18.0.1")

    @override_settings(AUDIT_TRUST_FORWARDED_FOR=True)
    def test_should_use_the_first_forwarded_for_address_when_trusted(self):
        request = self._request(
            self.user,
            REMOTE_ADDR="172.18.0.1",
            HTTP_X_FORWARDED_FOR="198.51.100.9, 10.0.0.1",
        )

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.ip_address, "198.51.100.9")

    @override_settings(AUDIT_TRUST_FORWARDED_FOR=True)
    def test_should_fall_back_to_the_remote_address_when_forwarded_for_is_invalid(self):
        request = self._request(
            self.user, REMOTE_ADDR="172.18.0.1", HTTP_X_FORWARDED_FOR="not-an-ip"
        )

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.ip_address, "172.18.0.1")

    def test_should_still_record_the_event_when_no_valid_address_is_available(self):
        request = self._request(self.user, REMOTE_ADDR="not-an-ip")

        audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        entry = AuditLog.objects.get()
        self.assertIsNone(entry.ip_address)
        self.assertEqual(entry.action, AuditAction.DOC_DOWNLOAD)

    def test_should_not_raise_when_the_insert_fails(self):
        request = self._request(self.user)

        with (
            mock.patch.object(AuditLog.objects, "create", side_effect=DatabaseError("boom")),
            self.assertLogs(LOGGER_NAME, level="ERROR"),
        ):
            result = audit_service.log_event(request, AuditAction.DOC_DOWNLOAD, "document", 3)

        self.assertIsNone(result)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_keep_the_connection_usable_after_a_database_level_failure(self):
        request = self._request(self.user)

        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            audit_service.log_event(request, "NOT_AN_ACTION", "document", 3)

        self.assertEqual(AuditLog.objects.count(), 0)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_should_not_raise_when_details_are_not_serializable(self):
        request = self._request(self.user)

        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            audit_service.log_event(
                request,
                AuditAction.DOC_DOWNLOAD,
                "document",
                3,
                details={"value": object()},
            )

        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_record_a_new_temp_upload(self):
        request = self._request(self.user)
        result = {
            "revision_created": False,
            "temp_file_id": "abc",
            "original_name": "relatorio.pdf",
            "sha256": "hash",
        }

        audit_service.log_temp_upload(request, result)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditAction.DOC_UPLOAD_SUCCESS)
        self.assertEqual(entry.entity, "temp_upload")
        self.assertIsNone(entry.entity_id)
        self.assertEqual(entry.record["temp_file_id"], "abc")
        self.assertEqual(entry.record["original_name"], "relatorio.pdf")
        self.assertEqual(entry.record["sha256"], "hash")

    def test_should_record_an_upload_that_created_a_new_revision_against_the_document(self):
        request = self._request(self.user)
        result = {"revision_created": True, "document": {"id": 7, "version": 2}, "sha256": "hash"}

        audit_service.log_temp_upload(request, result)

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditAction.DOC_UPLOAD_SUCCESS)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, 7)
        self.assertTrue(entry.record["revision_created"])
        self.assertEqual(entry.record["version"], 2)

    def test_should_record_a_duplicate_attempt_against_the_existing_document(self):
        request = self._request(self.user)
        existing_file = SimpleNamespace(
            sha256="hash",
            revision=SimpleNamespace(document=SimpleNamespace(id=7, code="RA-0001")),
        )

        audit_service.log_duplicate_attempt(
            request,
            existing_file,
            audit_service.STAGE_UPLOAD,
            {"original_name": "copia.pdf"},
        )

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditAction.DOC_UPLOAD_DUPLICATE)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, 7)
        self.assertEqual(
            {key: entry.record[key] for key in ("stage", "document_code", "sha256")},
            {"stage": "upload", "document_code": "RA-0001", "sha256": "hash"},
        )
        self.assertEqual(entry.record["original_name"], "copia.pdf")

    def test_should_record_a_submitted_document(self):
        request = self._request(self.user)
        document = SimpleNamespace(id=12, code="AK-2100-EST-DWG-0001")

        audit_service.log_document_submitted(request, document, {"temp_file_id": "tmp"})

        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, AuditAction.DOC_SUBMIT_SUCCESS)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, 12)
        self.assertEqual(entry.record["document_code"], "AK-2100-EST-DWG-0001")
        self.assertEqual(entry.record["temp_file_id"], "tmp")

    def test_should_not_raise_when_the_builder_input_is_malformed(self):
        request = self._request(self.user)

        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            audit_service.log_temp_upload(request, {})

        self.assertEqual(AuditLog.objects.count(), 0)

class ClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_should_use_the_first_forwarded_address_when_behind_a_proxy(self):
        request = self.factory.post(
            "/documents", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1", REMOTE_ADDR="172.18.0.1"
        )

        ip = client_ip(request)

        self.assertEqual(ip, "203.0.113.7")

    def test_should_fall_back_to_the_remote_address(self):
        request = self.factory.post("/documents", REMOTE_ADDR="198.51.100.20")

        ip = client_ip(request)

        self.assertEqual(ip, "198.51.100.20")

    def test_should_ignore_a_forwarded_value_that_is_not_an_ip(self):
        request = self.factory.post(
            "/documents", HTTP_X_FORWARDED_FOR="not-an-ip", REMOTE_ADDR="198.51.100.20"
        )

        ip = client_ip(request)

        self.assertEqual(ip, "198.51.100.20")

    def test_should_return_none_when_no_valid_address_is_available(self):
        request = self.factory.post("/documents", REMOTE_ADDR="")

        ip = client_ip(request)

        self.assertIsNone(ip)

    def test_should_accept_ipv6_addresses(self):
        request = self.factory.post("/documents", HTTP_X_FORWARDED_FOR="2001:db8::1")

        ip = client_ip(request)

        self.assertEqual(ip, "2001:db8::1")


class ClientUserAgentTests(TestCase):
    def test_should_truncate_a_very_long_user_agent(self):
        request = RequestFactory().post("/documents", HTTP_USER_AGENT="x" * 2000)

        user_agent = client_user_agent(request)

        self.assertEqual(len(user_agent), USER_AGENT_MAX_LENGTH)

    def test_should_return_an_empty_string_without_the_header(self):
        request = RequestFactory().post("/documents")

        user_agent = client_user_agent(request)

        self.assertEqual(user_agent, "")


class RecordDocumentCreatedTests(TestCase):
    def setUp(self):
        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=area
        )
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="DWG", name="Desenho"),
            responsible=self.user,
        )
        Revision.objects.create(document=self.document, version=1, author=self.user)
        self.request = RequestFactory().post(
            "/documents",
            HTTP_X_FORWARDED_FOR="203.0.113.7",
            HTTP_USER_AGENT="Mozilla/5.0 (test)",
        )

    def test_should_store_who_what_when_and_where(self):
        entry = record_document_created(self.document, self.request)

        entry.refresh_from_db()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, AuditAction.CREATE)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, self.document.id)
        self.assertEqual(entry.ip_address, "203.0.113.7")
        self.assertIsNotNone(entry.occurred_at)
        self.assertEqual(
            entry.record,
            {
                "event": "DOCUMENT_CREATED",
                "code": "AK-2100-EST-DWG-0001",
                "title": "Desenho da caverna 14",
                "version": 1,
                "revision": "REV01",
                "user_agent": "Mozilla/5.0 (test)",
            },
        )

    def test_should_record_the_timestamp_in_utc(self):
        entry = record_document_created(self.document, self.request)

        entry.refresh_from_db()
        self.assertEqual(entry.occurred_at.utcoffset().total_seconds(), 0)

    def test_should_return_none_and_log_instead_of_raising_when_the_write_fails(self):
        with (
            mock.patch.object(AuditLog.objects, "create", side_effect=RuntimeError("db down")),
            self.assertLogs("core.services.audit_service", level="ERROR") as logs,
        ):
            entry = record_document_created(self.document, self.request)

        self.assertIsNone(entry)
        self.assertIn("DOCUMENT_CREATED", "\n".join(logs.output))
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_leave_the_surrounding_transaction_usable_after_a_database_error(self):
        with (
            mock.patch(
                "core.services.audit_service.client_ip", return_value="definitely-not-an-ip"
            ),
            self.assertLogs("core.services.audit_service", level="ERROR"),
        ):
            entry = record_document_created(self.document, self.request)

        self.assertIsNone(entry)
        self.assertTrue(Document.objects.filter(pk=self.document.pk).exists())

