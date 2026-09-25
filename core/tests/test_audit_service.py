from unittest import mock

from django.test import RequestFactory, TestCase
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
from core.services.audit_service import (
    DOCUMENT_ACCESS_DENIED_EVENT,
    DOCUMENT_CREATED_EVENT,
    USER_AGENT_MAX_LENGTH,
    client_ip,
    client_user_agent,
    record_document_access_denied,
    record_document_created,
)


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
            created_by=self.user,
            updated_by=self.user,
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
                "event": DOCUMENT_CREATED_EVENT,
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
        self.assertIsNotNone(entry.occurred_at.tzinfo)
        self.assertEqual(entry.occurred_at.utcoffset(), timezone.timedelta(0))

    def test_should_return_none_and_log_instead_of_raising_when_the_write_fails(self):
        with (
            mock.patch(
                "core.services.audit_service.AuditLog.objects.create",
                side_effect=RuntimeError("db down"),
            ),
            self.assertLogs("core.services.audit_service", level="ERROR") as logs,
        ):
            entry = record_document_created(self.document, self.request)

        self.assertIsNone(entry)
        self.assertIn(DOCUMENT_CREATED_EVENT, "\n".join(logs.output))

    def test_should_leave_the_surrounding_transaction_usable_after_a_database_error(self):
        with (
            mock.patch(
                "core.services.audit_service.AuditLog.objects.create",
                side_effect=RuntimeError("db down"),
            ),
            self.assertLogs("core.services.audit_service", level="ERROR"),
        ):
            entry = record_document_created(self.document, self.request)

        self.assertIsNone(entry)
        # A savepoint rollback must leave the outer transaction usable:
        # a query after the failure has to work.
        self.assertTrue(Document.objects.filter(pk=self.document.pk).exists())


class RecordDocumentAccessDeniedTests(TestCase):
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
            created_by=self.user,
            updated_by=self.user,
        )
        self.request = RequestFactory().post(
            "/documents",
            HTTP_X_FORWARDED_FOR="203.0.113.7",
            HTTP_USER_AGENT="Mozilla/5.0 (test)",
        )

    def test_should_store_who_what_when_and_where(self):
        entry = record_document_access_denied(self.document, self.user, self.request)

        entry.refresh_from_db()
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.action, AuditAction.READ)
        self.assertEqual(entry.entity, "document")
        self.assertEqual(entry.entity_id, self.document.id)
        self.assertEqual(entry.ip_address, "203.0.113.7")
        self.assertEqual(
            entry.record,
            {
                "event": DOCUMENT_ACCESS_DENIED_EVENT,
                "code": "AK-2100-EST-DWG-0001",
                "outcome": "denied",
                "user_agent": "Mozilla/5.0 (test)",
            },
        )

    def test_should_return_none_and_log_instead_of_raising_when_the_write_fails(self):
        with (
            mock.patch(
                "core.services.audit_service.AuditLog.objects.create",
                side_effect=RuntimeError("db down"),
            ),
            self.assertLogs("core.services.audit_service", level="ERROR") as logs,
        ):
            entry = record_document_access_denied(self.document, self.user, self.request)

        self.assertIsNone(entry)
        self.assertIn(DOCUMENT_ACCESS_DENIED_EVENT, "\n".join(logs.output))
