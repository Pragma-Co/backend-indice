from datetime import timedelta
from io import StringIO
from smtplib import SMTPException
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend
from django.core.management import CommandError, call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    DataIncident,
    DataIncidentSubjectNotification,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    IncidentStatus,
    Project,
    Revision,
    RevisionStatus,
    Role,
    SubjectNotificationReason,
    SubjectNotificationStatus,
    User,
)
from core.services import audit_service
from core.services.data_incident_exceptions import (
    IncidentClosedError,
    IncidentNotFoundError,
    NoAffectedUsersError,
)
from core.services.data_incident_service import add_action, register_incident
from core.services.incident_subject_notification_service import (
    MAX_ATTEMPTS,
    identify_affected_users,
    notify_affected_users,
    subject_notifications_overview,
)

CONTAINMENT = "Pedido de exclusão da planilha enviado ao fornecedor."


def failing_for(email):
    original = EmailBackend.send_messages

    def send_messages(self, messages):
        if any(message.to == [email] for message in messages):
            raise SMTPException("mailbox unavailable")
        return original(self, messages)

    return mock.patch.object(EmailBackend, "send_messages", send_messages)


class SubjectNotificationFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.admin = self._user("admin@example.com", Role.ADMIN)
        self.auditor = self._user("auditor@example.com", Role.AUDITOR)
        self.listed = self._user("listed@example.com", Role.VIEWER)
        self.responsible = self._user("responsible@example.com", Role.AUTHOR)
        self.reviewer = self._user("reviewer@example.com", Role.AUDITOR)
        self.requester = self._user("requester@example.com", Role.VIEWER)
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="DWG", name="Desenho"),
            responsible=self.responsible,
            created_by=self.responsible,
        )
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.PENDING,
            issue_date=timezone.localdate(),
            author=self.reviewer,
        )
        DocumentAccess.objects.create(
            document=self.document,
            user=self.requester,
            justification="Preciso consultar o desenho para a inspeção.",
            requested_at=timezone.now(),
        )
        self.incident = self._register()
        self.client = Client()

    def _user(self, email, role):
        return User.objects.create_user(
            email=email, password="secret", name=email.split("@")[0], role=role, area=self.area
        )

    def _register(self, **overrides):
        now = timezone.now()
        payload = {
            "title": "Planilha com e-mails enviada ao fornecedor errado",
            "description": "Relatório de horas com nome, e-mail e senha provisória de engenheiros.",
            "incident_type": "MISDIRECTED_DELIVERY",
            "severity": "HIGH",
            "occurred_at": (now - timedelta(days=2)).isoformat(),
            "detected_at": (now - timedelta(days=1)).isoformat(),
            "affected_data_categories": ["IDENTIFICATION", "CREDENTIALS"],
            "affected_subjects_count": 4,
            "affected_user_ids": [self.listed.id],
            "affected_document_ids": [self.document.id],
        }
        payload.update(overrides)
        return register_incident(payload, self.admin)

    def _contain(self):
        return add_action(
            self.incident.id, {"kind": "CONTAINMENT", "description": CONTAINMENT}, self.admin
        )

    def _rows(self):
        return {
            row.user.email: row
            for row in DataIncidentSubjectNotification.objects.filter(
                incident=self.incident
            ).select_related("user")
        }

    def _message_to(self, email):
        return next(message for message in mail.outbox if message.to == [email])


class IdentifyAffectedUsersTests(SubjectNotificationFixtureMixin, TestCase):
    def test_should_identify_listed_users_and_people_linked_to_the_affected_documents(self):
        recipients = identify_affected_users(self.incident)

        self.assertEqual(
            recipients,
            [
                (self.listed, SubjectNotificationReason.AFFECTED_USER),
                (self.responsible, SubjectNotificationReason.DOCUMENT_RESPONSIBLE),
                (self.reviewer, SubjectNotificationReason.REVISION_AUTHOR),
                (self.requester, SubjectNotificationReason.DOCUMENT_ACCESS),
            ],
        )

    def test_should_skip_inactive_users_when_identifying_recipients(self):
        User.objects.filter(pk=self.listed.pk).update(is_active=False)

        recipients = identify_affected_users(self.incident)

        self.assertNotIn(self.listed, [user for user, _reason in recipients])

    def test_should_keep_the_first_reason_when_a_user_matches_several(self):
        incident = self._register(affected_user_ids=[self.responsible.id])

        recipients = dict(identify_affected_users(incident))

        self.assertEqual(recipients[self.responsible], SubjectNotificationReason.AFFECTED_USER)


class NotifyAffectedUsersServiceTests(SubjectNotificationFixtureMixin, TestCase):
    def test_should_send_the_communication_to_every_identified_user(self):
        result = notify_affected_users(self.incident.id)

        rows = self._rows()
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(result["outcome"], {"sent": 4, "failed": 0, "skipped": 0})
        self.assertEqual({row.status for row in rows.values()}, {SubjectNotificationStatus.SENT})
        self.assertEqual({row.attempts for row in rows.values()}, {1})
        self.assertTrue(all(row.sent_at is not None for row in rows.values()))
        self.assertEqual(rows["requester@example.com"].reason, "DOCUMENT_ACCESS")

    def test_should_render_the_official_template_with_incident_data_and_guidance(self):
        self._contain()

        notify_affected_users(self.incident.id)

        message = self._message_to("listed@example.com")
        self.assertEqual(
            message.subject,
            f"[Índice] Comunicado sobre incidente de segurança {self.incident.reference}",
        )
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn("Prezado(a) listed,", message.body)
        self.assertIn(self.incident.reference, message.body)
        self.assertIn("envio a destinatário incorreto", message.body)
        self.assertIn("- dados de identificação (nome, e-mail)", message.body)
        self.assertIn("- credenciais de acesso", message.body)
        self.assertIn(f"- {CONTAINMENT}", message.body)
        self.assertIn("Troque imediatamente sua senha", message.body)
        self.assertIn("(ANPD) será comunicada", message.body)
        self.assertIn(settings.INCIDENT_CONTACT_EMAIL, message.body)
        self.assertEqual(message.alternatives[0][1], "text/html")
        self.assertIn(f"<strong>{self.incident.reference}</strong>", message.alternatives[0][0])

    def test_should_mark_the_data_subjects_as_notified_when_everyone_receives_it(self):
        notify_affected_users(self.incident.id)

        self.incident.refresh_from_db()

        self.assertIsNotNone(self.incident.subjects_notified_at)

    def test_should_record_the_failure_and_keep_sending_to_the_others(self):
        with failing_for("requester@example.com"):
            result = notify_affected_users(self.incident.id)

        rows = self._rows()
        self.incident.refresh_from_db()
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(result["outcome"], {"sent": 3, "failed": 1, "skipped": 0})
        self.assertEqual(rows["requester@example.com"].status, SubjectNotificationStatus.FAILED)
        self.assertEqual(rows["requester@example.com"].attempts, 1)
        self.assertEqual(rows["requester@example.com"].last_error, "SMTPException")
        self.assertIsNone(rows["requester@example.com"].sent_at)
        self.assertEqual(rows["listed@example.com"].status, SubjectNotificationStatus.SENT)
        self.assertIsNone(self.incident.subjects_notified_at)

    def test_should_retry_only_the_failed_communications(self):
        with failing_for("requester@example.com"):
            notify_affected_users(self.incident.id)

        result = notify_affected_users(self.incident.id)

        rows = self._rows()
        self.incident.refresh_from_db()
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(result["outcome"], {"sent": 1, "failed": 0, "skipped": 3})
        self.assertEqual(rows["requester@example.com"].status, SubjectNotificationStatus.SENT)
        self.assertEqual(rows["requester@example.com"].attempts, 2)
        self.assertEqual(rows["requester@example.com"].last_error, "")
        self.assertIsNotNone(self.incident.subjects_notified_at)

    def test_should_stop_retrying_after_the_maximum_attempts(self):
        with failing_for("requester@example.com"):
            notify_affected_users(self.incident.id)
        DataIncidentSubjectNotification.objects.filter(user=self.requester).update(
            attempts=MAX_ATTEMPTS
        )

        result = notify_affected_users(self.incident.id)

        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(result["outcome"], {"sent": 0, "failed": 0, "skipped": 4})
        self.assertEqual(result["summary"]["exhausted"], 1)
        self.assertEqual(result["summary"]["failed"], 1)

    def test_should_not_send_again_to_users_already_notified(self):
        notify_affected_users(self.incident.id)

        result = notify_affected_users(self.incident.id)

        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(result["outcome"], {"sent": 0, "failed": 0, "skipped": 4})

    def test_should_refuse_a_closed_incident(self):
        DataIncident.objects.filter(pk=self.incident.pk).update(
            status=IncidentStatus.CLOSED, closed_at=timezone.now()
        )

        with self.assertRaises(IncidentClosedError):
            notify_affected_users(self.incident.id)

        self.assertEqual(mail.outbox, [])

    def test_should_refuse_an_incident_without_affected_users(self):
        incident = self._register(affected_user_ids=[], affected_document_ids=[])

        with self.assertRaises(NoAffectedUsersError):
            notify_affected_users(incident.id)

        with self.assertRaises(IncidentNotFoundError):
            notify_affected_users(999999)

    def test_should_preview_the_recipients_without_persisting_them(self):
        overview = subject_notifications_overview(self.incident.id)

        self.assertEqual(overview["summary"]["identified"], 4)
        self.assertEqual(overview["summary"]["pending"], 4)
        self.assertEqual(DataIncidentSubjectNotification.objects.count(), 0)
        self.assertIn("Prezado(a) colaborador(a),", overview["preview"]["text"])
        self.assertEqual(mail.outbox, [])

    def test_should_keep_the_record_of_a_user_deactivated_after_the_communication(self):
        notify_affected_users(self.incident.id)
        User.objects.filter(pk=self.listed.pk).update(is_active=False)

        overview = subject_notifications_overview(self.incident.id)

        statuses = {row.user.email: row.status for row in overview["recipients"]}
        self.assertEqual(statuses["listed@example.com"], SubjectNotificationStatus.SENT)
        self.assertEqual(overview["summary"]["identified"], 4)


class SubjectNotificationViewTests(SubjectNotificationFixtureMixin, TestCase):
    def _url(self, incident_id=None):
        return reverse(
            "security-incident-subject-notifications", args=[incident_id or self.incident.id]
        )

    def test_should_answer_the_overview_and_audit_the_read(self):
        self.client.force_login(self.admin)

        response = self.client.get(self._url())

        body = response.json()
        audit = AuditLog.objects.filter(entity="data_incident", action=AuditAction.READ).last()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["incident"]["reference"], self.incident.reference)
        self.assertEqual(body["summary"]["identified"], 4)
        self.assertEqual(
            [item["user"]["name"] for item in body["recipients"]],
            ["listed", "requester", "responsible", "reviewer"],
        )
        self.assertEqual(body["recipients"][0]["status"], "PENDING")
        self.assertIn(self.incident.reference, body["preview"]["subject"])
        self.assertEqual(audit.record["event"], "INCIDENT_SUBJECT_NOTIFICATIONS_VIEWED")

    def test_should_send_the_communications_and_write_the_audit_entry(self):
        self.client.force_login(self.admin)

        response = self.client.post(self._url(), data="{}", content_type="application/json")

        body = response.json()
        audit = AuditLog.objects.get(
            entity="data_incident", record__event="INCIDENT_SUBJECTS_NOTIFIED"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["result"], {"sent": 4, "failed": 0, "skipped": 0})
        self.assertEqual(body["summary"]["sent"], 4)
        self.assertIsNotNone(body["incident"]["subjects_notified_at"])
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(audit.action, AuditAction.UPDATE)
        self.assertEqual(audit.user, self.admin)
        self.assertEqual(audit.record["sent"], 4)
        self.assertEqual(audit.record["reference"], self.incident.reference)

    def test_should_answer_409_without_recipients_and_404_for_an_unknown_incident(self):
        incident = self._register(affected_user_ids=[], affected_document_ids=[])
        self.client.force_login(self.admin)

        empty = self.client.post(self._url(incident.id))
        unknown = self.client.post(self._url(999999))

        self.assertEqual(empty.status_code, 409)
        self.assertEqual(empty.json(), {"error": "NoAffectedUsers"})
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json(), {"error": "IncidentNotFound"})

    def test_should_restrict_the_routes_to_administrators(self):
        anonymous = Client()
        self.client.force_login(self.auditor)

        responses = [
            anonymous.get(self._url()),
            anonymous.post(self._url()),
            self.client.get(self._url()),
            self.client.post(self._url()),
        ]

        self.assertEqual([response.status_code for response in responses], [401, 401, 403, 403])
        self.assertEqual(mail.outbox, [])
        self.assertEqual(DataIncidentSubjectNotification.objects.count(), 0)

    def test_should_answer_503_but_keep_the_sent_records_when_the_audit_cannot_be_written(self):
        self.client.force_login(self.admin)

        with mock.patch.object(
            audit_service, "log_event_required", side_effect=audit_service.AuditLogWriteError()
        ):
            response = self.client.post(self._url())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "AuditUnavailable"})
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(
            DataIncidentSubjectNotification.objects.filter(
                status=SubjectNotificationStatus.SENT
            ).count(),
            4,
        )


class SendIncidentNotificationsCommandTests(SubjectNotificationFixtureMixin, TestCase):
    def test_should_retry_failed_communications_from_the_command(self):
        with failing_for("requester@example.com"):
            notify_affected_users(self.incident.id)
        output = StringIO()

        call_command("send_incident_notifications", stdout=output)

        self.assertEqual(len(mail.outbox), 4)
        self.assertIn(f"{self.incident.reference}: sent 1, failed 0, skipped 3", output.getvalue())
        self.assertEqual(
            self._rows()["requester@example.com"].status, SubjectNotificationStatus.SENT
        )

    def test_should_fail_the_command_when_a_communication_still_fails(self):
        with failing_for("requester@example.com"):
            notify_affected_users(self.incident.id)

            with self.assertRaises(CommandError):
                call_command("send_incident_notifications", incident=self.incident.id)

        self.assertEqual(self._rows()["requester@example.com"].attempts, 2)

    def test_should_report_when_nothing_is_pending(self):
        notify_affected_users(self.incident.id)
        output = StringIO()

        call_command("send_incident_notifications", stdout=output)

        self.assertEqual(output.getvalue().strip(), "No pending communications.")
        self.assertEqual(len(mail.outbox), 4)
