from datetime import datetime, timedelta
from unittest import mock

from django.db import DatabaseError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    AuditLog,
    BackupRun,
    DataIncident,
    DataIncidentAction,
    DataIncidentStatusChange,
    Discipline,
    Document,
    DocumentType,
    IncidentStatus,
    Project,
    Role,
    User,
)
from core.models.choices import BackupTarget
from core.serializers.data_incident_serializer import serialize_incident_summary
from core.services.data_incident_exceptions import (
    IncidentClosedError,
    IncidentClosureBlockedError,
    IncidentQueryError,
    IncidentValidationError,
    InvalidStatusTransitionError,
)
from core.services.data_incident_service import (
    CLOSURE_AUTHORITY_NOT_NOTIFIED,
    CLOSURE_NO_ACTIONS,
    CLOSURE_SUBJECTS_NOT_NOTIFIED,
    add_action,
    add_business_days,
    change_status,
    get_incident,
    list_incidents,
    record_notification,
    register_incident,
    update_incident,
)


class DataIncidentFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.admin = self._user("admin@example.com", Role.ADMIN)
        self.second_admin = self._user("second.admin@example.com", Role.ADMIN)
        self.auditor = self._user("auditor@example.com", Role.AUDITOR)
        self.viewer = self._user("viewer@example.com", Role.VIEWER)
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="DWG", name="Desenho"),
            responsible=self.admin,
            created_by=self.admin,
        )
        self.client = Client()

    def _user(self, email, role):
        return User.objects.create_user(
            email=email, password="secret", name=email.split("@")[0], role=role, area=self.area
        )

    def _payload(self, **overrides):
        now = timezone.now()
        payload = {
            "title": "Planilha com e-mails enviada ao fornecedor errado",
            "description": "Relatório de horas com nome e e-mail de 12 engenheiros.",
            "incident_type": "MISDIRECTED_DELIVERY",
            "severity": "HIGH",
            "occurred_at": (now - timedelta(days=2)).isoformat(),
            "detected_at": (now - timedelta(days=1)).isoformat(),
            "affected_data_categories": ["IDENTIFICATION", "PROFESSIONAL"],
            "affected_subjects_count": 12,
            "affected_user_ids": [self.viewer.id],
            "affected_document_ids": [self.document.id],
        }
        payload.update(overrides)
        return payload

    def _register(self, **overrides):
        return register_incident(self._payload(**overrides), self.admin)

    def _contain(self, incident):
        return add_action(
            incident.id,
            {"kind": "CONTAINMENT", "description": "Pedido de exclusão enviado ao fornecedor."},
            self.admin,
        )

    def _notify_subjects(self, incident):
        return record_notification(incident.id, {"recipient": "DATA_SUBJECTS"}, self.admin)


class DataIncidentServiceTests(DataIncidentFixtureMixin, TestCase):
    def test_should_register_an_incident_with_reference_affected_data_and_history(self):
        incident = self._register()

        stored = get_incident(incident.id)
        self.assertEqual(stored.reference, f"INC-{timezone.localtime().year}-0001")
        self.assertEqual(stored.status, IncidentStatus.REPORTED)
        self.assertEqual(stored.affected_data_categories, ["IDENTIFICATION", "PROFESSIONAL"])
        self.assertEqual(list(stored.affected_users.all()), [self.viewer])
        self.assertEqual(list(stored.affected_documents.all()), [self.document])
        self.assertEqual(stored.reported_by, self.admin)
        self.assertTrue(stored.authority_notification_required)
        self.assertEqual(
            stored.authority_notification_due_at, add_business_days(stored.detected_at, 3)
        )
        self.assertEqual(
            [(change.from_status, change.to_status) for change in stored.status_changes.all()],
            [("", IncidentStatus.REPORTED)],
        )

    def test_should_number_references_sequentially_within_the_year(self):
        first = self._register()
        second = self._register(title="Segundo incidente")

        year = timezone.localtime().year
        self.assertEqual(
            [first.reference, second.reference], [f"INC-{year}-0001", f"INC-{year}-0002"]
        )

    def test_should_count_the_authority_deadline_in_business_days(self):
        friday_noon = timezone.make_aware(datetime(2026, 10, 30, 12, 0))

        deadline = add_business_days(friday_noon, 3)

        self.assertEqual(deadline.date(), datetime(2026, 11, 4).date())
        self.assertEqual(deadline.weekday(), 2)
        self.assertEqual((deadline.hour, deadline.minute), (12, 0))

    def test_should_require_authority_notification_from_medium_severity_by_default(self):
        low = self._register(severity="LOW")
        medium = self._register(title="Médio", severity="MEDIUM")
        forced = self._register(
            title="Baixo mas comunicado", severity="LOW", authority_notification_required=True
        )

        self.assertFalse(low.authority_notification_required)
        self.assertIsNone(low.authority_notification_due_at)
        self.assertTrue(medium.authority_notification_required)
        self.assertIsNotNone(medium.authority_notification_due_at)
        self.assertTrue(forced.authority_notification_required)
        self.assertIsNotNone(forced.authority_notification_due_at)

    def test_should_reject_an_invalid_registration(self):
        future = (timezone.now() + timedelta(days=1)).isoformat()

        with self.assertRaises(IncidentValidationError) as raised:
            self._register(
                title="   ",
                incident_type="GOSSIP",
                occurred_at=future,
                affected_data_categories=["DNA"],
                affected_user_ids=[999999],
                assigned_to_id=self.auditor.id,
            )

        codes = {field: error["code"] for field, error in raised.exception.errors.items()}
        self.assertEqual(
            codes,
            {
                "title": "required",
                "incident_type": "invalid_choice",
                "occurred_at": "in_the_future",
                "affected_data_categories": "invalid_choice",
                "affected_user_ids": "not_found",
                "assigned_to_id": "not_security_officer",
            },
        )

    def test_should_reject_a_detection_earlier_than_the_occurrence(self):
        now = timezone.now()

        with self.assertRaises(IncidentValidationError) as raised:
            self._register(
                occurred_at=(now - timedelta(hours=1)).isoformat(),
                detected_at=(now - timedelta(hours=2)).isoformat(),
            )

        self.assertEqual(raised.exception.errors["detected_at"]["code"], "before_occurrence")

    def test_should_follow_the_lifecycle_and_keep_the_status_history(self):
        incident = self._register()
        self._contain(incident)
        record_notification(incident.id, {"recipient": "AUTHORITY"}, self.admin)
        self._notify_subjects(incident)

        for status in ("CONTAINMENT", "ANALYSIS", "RESOLVED", "CLOSED"):
            incident = change_status(
                incident.id, {"status": status, "note": f"para {status}"}, self.admin
            )

        stored = get_incident(incident.id)
        self.assertEqual(stored.status, IncidentStatus.CLOSED)
        self.assertIsNotNone(stored.resolved_at)
        self.assertIsNotNone(stored.closed_at)
        self.assertEqual(
            [change.to_status for change in stored.status_changes.all()],
            ["REPORTED", "CONTAINMENT", "ANALYSIS", "RESOLVED", "CLOSED"],
        )
        self.assertEqual(stored.status_changes.last().changed_by, self.admin)

    def test_should_reject_skipped_transitions(self):
        incident = self._register()

        with self.assertRaises(InvalidStatusTransitionError) as raised:
            change_status(incident.id, {"status": "RESOLVED"}, self.admin)

        self.assertEqual(
            (raised.exception.current, raised.exception.requested), ("REPORTED", "RESOLVED")
        )

    def test_should_block_closure_without_actions_or_the_required_notifications(self):
        incident = self._register()
        change_status(incident.id, {"status": "ANALYSIS"}, self.admin)
        change_status(incident.id, {"status": "RESOLVED"}, self.admin)

        with self.assertRaises(IncidentClosureBlockedError) as first:
            change_status(incident.id, {"status": "CLOSED"}, self.admin)
        self._contain(incident)
        with self.assertRaises(IncidentClosureBlockedError) as second:
            change_status(incident.id, {"status": "CLOSED"}, self.admin)
        record_notification(incident.id, {"recipient": "AUTHORITY"}, self.admin)
        with self.assertRaises(IncidentClosureBlockedError) as third:
            change_status(incident.id, {"status": "CLOSED"}, self.admin)
        self._notify_subjects(incident)
        closed = change_status(incident.id, {"status": "CLOSED"}, self.admin)

        self.assertEqual(
            first.exception.reasons,
            [CLOSURE_NO_ACTIONS, CLOSURE_AUTHORITY_NOT_NOTIFIED, CLOSURE_SUBJECTS_NOT_NOTIFIED],
        )
        self.assertEqual(
            second.exception.reasons,
            [CLOSURE_AUTHORITY_NOT_NOTIFIED, CLOSURE_SUBJECTS_NOT_NOTIFIED],
        )
        self.assertEqual(third.exception.reasons, [CLOSURE_SUBJECTS_NOT_NOTIFIED])
        self.assertEqual(closed.status, IncidentStatus.CLOSED)

    def test_should_freeze_a_closed_incident(self):
        incident = self._register(severity="LOW")
        self._contain(incident)
        self._notify_subjects(incident)
        for status in ("ANALYSIS", "RESOLVED", "CLOSED"):
            change_status(incident.id, {"status": status}, self.admin)

        with self.assertRaises(IncidentClosedError):
            self._contain(incident)
        with self.assertRaises(IncidentClosedError):
            update_incident(incident.id, {"root_cause": "x"}, self.admin)
        with self.assertRaises(IncidentClosedError):
            record_notification(incident.id, {"recipient": "DATA_SUBJECTS"}, self.admin)
        with self.assertRaises(InvalidStatusTransitionError):
            change_status(incident.id, {"status": "ANALYSIS"}, self.admin)

    def test_should_clear_the_resolution_when_the_analysis_is_reopened(self):
        incident = self._register(severity="LOW")
        change_status(incident.id, {"status": "ANALYSIS"}, self.admin)
        change_status(incident.id, {"status": "RESOLVED"}, self.admin)

        reopened = change_status(incident.id, {"status": "ANALYSIS"}, self.admin)

        self.assertIsNone(reopened.resolved_at)
        self.assertEqual(reopened.status, IncidentStatus.ANALYSIS)

    def test_should_record_actions_with_who_performed_and_who_recorded_them(self):
        incident = self._register()

        action = add_action(
            incident.id,
            {
                "kind": "COMMUNICATION",
                "description": "Titulares avisados por e-mail.",
                "performed_by_id": self.second_admin.id,
                "performed_at": (timezone.now() - timedelta(hours=3)).isoformat(),
            },
            self.admin,
        )

        self.assertEqual(action.performed_by, self.second_admin)
        self.assertEqual(action.recorded_by, self.admin)
        self.assertEqual(list(get_incident(incident.id).actions.all()), [action])

    def test_should_update_the_responsible_and_recompute_the_deadline(self):
        incident = self._register()

        updated, changed = update_incident(
            incident.id,
            {"assigned_to_id": self.second_admin.id, "authority_notification_required": False},
            self.admin,
        )
        required_again, _ = update_incident(
            incident.id, {"authority_notification_required": True}, self.admin
        )

        self.assertEqual(updated.assigned_to, self.second_admin)
        self.assertIsNone(updated.authority_notification_due_at)
        self.assertIn("assigned_to", changed)
        self.assertEqual(
            required_again.authority_notification_due_at,
            add_business_days(incident.detected_at, 3),
        )

    def test_should_reject_unknown_fields_on_update(self):
        incident = self._register()

        with self.assertRaises(IncidentValidationError) as raised:
            update_incident(incident.id, {"status": "CLOSED"}, self.admin)

        self.assertEqual(raised.exception.errors["body"]["code"], "unknown_fields")

    def test_should_keep_the_status_history_append_only(self):
        incident = self._register()
        change = DataIncidentStatusChange.objects.get(incident=incident)

        with self.assertRaises(DatabaseError), transaction.atomic():
            DataIncidentStatusChange.objects.filter(pk=change.pk).update(note="editado")
        with self.assertRaises(DatabaseError), transaction.atomic():
            change.delete()

        self.assertEqual(DataIncidentStatusChange.objects.filter(incident=incident).count(), 1)

    def test_should_list_incidents_with_filters_and_flag_overdue_notifications(self):
        overdue = self._register(
            occurred_at=(timezone.now() - timedelta(days=11)).isoformat(),
            detected_at=(timezone.now() - timedelta(days=10)).isoformat(),
        )
        self._register(title="Baixo", severity="LOW")

        everything = list_incidents({}, serialize_incident_summary)
        only_overdue = list_incidents({"overdue": "true"}, serialize_incident_summary)
        only_low = list_incidents({"severity": "low"}, serialize_incident_summary)

        self.assertEqual(everything["count"], 2)
        self.assertEqual([item["id"] for item in only_overdue["results"]], [overdue.id])
        self.assertTrue(only_overdue["results"][0]["authority_notification"]["overdue"])
        self.assertEqual(only_low["count"], 1)
        with self.assertRaises(IncidentQueryError):
            list_incidents({"page": "0", "status": "WHATEVER"}, serialize_incident_summary)


class DataIncidentViewTests(DataIncidentFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def _events(self):
        return list(
            AuditLog.objects.filter(entity="data_incident")
            .order_by("id")
            .values_list("record__event", flat=True)
        )

    def test_should_register_list_and_detail_incidents_for_an_administrator(self):
        created = self.client.post(
            reverse("security-incident-list"),
            data=self._payload(),
            content_type="application/json",
        )
        listed = self.client.get(reverse("security-incident-list"))
        detail = self.client.get(reverse("security-incident-detail", args=[created.json()["id"]]))

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["reference"], f"INC-{timezone.localtime().year}-0001")
        self.assertEqual(created.json()["affected_documents"][0]["code"], self.document.code)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            [change["to_status"] for change in detail.json()["status_changes"]], ["REPORTED"]
        )
        self.assertEqual(
            self._events(), ["INCIDENT_REGISTERED", "INCIDENT_LIST_VIEWED", "INCIDENT_VIEWED"]
        )

    def test_should_record_actions_notifications_and_status_changes_through_the_api(self):
        incident = self._register()

        action = self.client.post(
            reverse("security-incident-actions", args=[incident.id]),
            data={"kind": "CONTAINMENT", "description": "Acesso do fornecedor revogado."},
            content_type="application/json",
        )
        notified = self.client.post(
            reverse("security-incident-notifications", args=[incident.id]),
            data={"recipient": "AUTHORITY"},
            content_type="application/json",
        )
        moved = self.client.post(
            reverse("security-incident-status", args=[incident.id]),
            data={"status": "CONTAINMENT", "note": "Contenção iniciada."},
            content_type="application/json",
        )
        updated = self.client.patch(
            reverse("security-incident-detail", args=[incident.id]),
            data={
                "assigned_to_id": self.second_admin.id,
                "root_cause": "Lista de e-mails desatualizada.",
            },
            content_type="application/json",
        )

        self.assertEqual(action.status_code, 201)
        self.assertEqual(action.json()["kind"], "CONTAINMENT")
        self.assertEqual(notified.status_code, 200)
        self.assertIsNotNone(notified.json()["authority_notification"]["notified_at"])
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.json()["status"], "CONTAINMENT")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["assigned_to"]["id"], self.second_admin.id)
        self.assertEqual(
            self._events(),
            [
                "INCIDENT_ACTION_RECORDED",
                "INCIDENT_NOTIFICATION_RECORDED",
                "INCIDENT_STATUS_CHANGED",
                "INCIDENT_UPDATED",
            ],
        )

    def test_should_answer_409_for_forbidden_transitions_and_blocked_closures(self):
        incident = self._register(severity="LOW")
        change_status(incident.id, {"status": "ANALYSIS"}, self.admin)
        change_status(incident.id, {"status": "RESOLVED"}, self.admin)

        skipped = self.client.post(
            reverse("security-incident-status", args=[incident.id]),
            data={"status": "CONTAINMENT"},
            content_type="application/json",
        )
        blocked = self.client.post(
            reverse("security-incident-status", args=[incident.id]),
            data={"status": "CLOSED"},
            content_type="application/json",
        )

        self.assertEqual(skipped.status_code, 409)
        self.assertEqual(skipped.json(), {"error": "InvalidStatusTransition", "status": "RESOLVED"})
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(
            blocked.json(),
            {
                "error": "IncidentClosureBlocked",
                "reasons": [CLOSURE_NO_ACTIONS, CLOSURE_SUBJECTS_NOT_NOTIFIED],
            },
        )

    def test_should_validate_the_body(self):
        invalid_json = self.client.post(
            reverse("security-incident-list"), data="{", content_type="application/json"
        )
        invalid_payload = self.client.post(
            reverse("security-incident-list"), data={}, content_type="application/json"
        )

        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(invalid_json.json(), {"error": "InvalidJSON"})
        self.assertEqual(invalid_payload.status_code, 400)
        self.assertEqual(invalid_payload.json()["errors"]["title"]["code"], "required")

    def test_should_answer_404_for_an_unknown_incident(self):
        response = self.client.get(reverse("security-incident-detail", args=[999999]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "IncidentNotFound"})

    def test_should_deny_non_administrators_and_anonymous_users(self):
        incident = self._register()
        self.client.force_login(self.auditor)
        forbidden = [
            self.client.get(reverse("security-incident-list")),
            self.client.post(
                reverse("security-incident-list"),
                data=self._payload(),
                content_type="application/json",
            ),
            self.client.get(reverse("security-incident-detail", args=[incident.id])),
            self.client.get(reverse("security-backup-list")),
        ]
        anonymous = Client().get(reverse("security-incident-list"))

        self.assertEqual([response.status_code for response in forbidden], [403, 403, 403, 403])
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(DataIncident.objects.count(), 1)

    def test_should_answer_503_and_register_nothing_when_the_audit_entry_fails(self):
        with mock.patch.object(AuditLog.objects, "create", side_effect=DatabaseError("boom")):
            response = self.client.post(
                reverse("security-incident-list"),
                data=self._payload(),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "AuditUnavailable"})
        self.assertEqual(DataIncident.objects.count(), 0)
        self.assertEqual(DataIncidentAction.objects.count(), 0)

    def test_should_list_backup_runs_for_administrators(self):
        BackupRun.objects.create(
            target=BackupTarget.POSTGRES,
            status="SUCCEEDED",
            destination="/app/backups/postgres/postgres-20261109T100000Z.json.gz.enc",
            size_bytes=2048,
            sha256="a" * 64,
            encrypted=True,
            record_count=120,
        )
        BackupRun.objects.create(target=BackupTarget.MONGODB, status="FAILED", error="Timeout")

        response = self.client.get(reverse("security-backup-list"), {"target": "postgres"})
        invalid = self.client.get(reverse("security-backup-list"), {"target": "sqlite"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        item = response.json()["results"][0]
        self.assertEqual(item["file_name"], "postgres-20261109T100000Z.json.gz.enc")
        self.assertEqual(item["record_count"], 120)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(
            list(
                AuditLog.objects.filter(entity="backup_run").values_list("record__event", flat=True)
            ),
            ["BACKUP_HISTORY_VIEWED"],
        )
