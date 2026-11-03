import json
from datetime import timedelta
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AccessStatus,
    AccessType,
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentAccess,
    DocumentArea,
    DocumentType,
    Project,
    Revision,
    RevisionStatus,
    User,
)
from core.services.access_request_exceptions import AccessRequestValidationError
from core.services.access_request_service import (
    JUSTIFICATION_MAX_LENGTH,
    JUSTIFICATION_MIN_LENGTH,
    pending_access_requests,
    validate_access_request_payload,
)
from core.services.documents_service import can_view_document

VALID_JUSTIFICATION = "Preciso do relatório para o plano de inspeção."


def _tomorrow():
    return timezone.localdate() + timedelta(days=1)


def _yesterday():
    return timezone.localdate() - timedelta(days=1)


class ValidateAccessRequestPayloadTests(TestCase):
    def _error_code(self, payload, field):
        with self.assertRaises(AccessRequestValidationError) as context:
            validate_access_request_payload(payload)
        return context.exception.errors[field]["code"]

    def _payload(self, **overrides):
        return {"justification": VALID_JUSTIFICATION, "access_type": "PERMANENT", **overrides}

    def test_should_clean_a_permanent_request(self):
        payload = self._payload(justification=f"  {VALID_JUSTIFICATION}  ")

        cleaned = validate_access_request_payload(payload)

        self.assertEqual(
            cleaned,
            {
                "justification": VALID_JUSTIFICATION,
                "access_type": AccessType.PERMANENT,
                "expires_on": None,
            },
        )

    def test_should_clean_a_temporary_request_with_a_lowercase_type(self):
        payload = self._payload(access_type="temporary", expires_on=_tomorrow().isoformat())

        cleaned = validate_access_request_payload(payload)

        self.assertEqual(cleaned["access_type"], AccessType.TEMPORARY)
        self.assertEqual(cleaned["expires_on"], _tomorrow())

    def test_should_accept_a_temporary_request_expiring_today(self):
        today = timezone.localdate()
        payload = self._payload(access_type="TEMPORARY", expires_on=today.isoformat())

        cleaned = validate_access_request_payload(payload)

        self.assertEqual(cleaned["expires_on"], today)

    def test_should_refuse_a_body_that_is_not_an_object(self):
        for payload in ([], "text", 1, None):
            with self.subTest(payload=payload):
                code = self._error_code(payload, "body")

                self.assertEqual(code, "invalid")

    def test_should_require_the_justification(self):
        for justification in (None, "", "   \n"):
            with self.subTest(justification=justification):
                code = self._error_code(self._payload(justification=justification), "justification")

                self.assertEqual(code, "required")

    def test_should_refuse_a_justification_that_is_not_a_string(self):
        for justification in (123, True, ["motivo"], {"text": "motivo"}):
            with self.subTest(justification=justification):
                code = self._error_code(self._payload(justification=justification), "justification")

                self.assertEqual(code, "invalid")

    def test_should_ignore_surrounding_spaces_when_measuring_the_justification(self):
        justification = " " * 10 + "x" * (JUSTIFICATION_MIN_LENGTH - 1) + " " * 10

        code = self._error_code(self._payload(justification=justification), "justification")

        self.assertEqual(code, "too_short")

    def test_should_accept_a_justification_at_the_length_limits(self):
        for length in (JUSTIFICATION_MIN_LENGTH, JUSTIFICATION_MAX_LENGTH):
            with self.subTest(length=length):
                cleaned = validate_access_request_payload(self._payload(justification="x" * length))

                self.assertEqual(len(cleaned["justification"]), length)

    def test_should_refuse_a_justification_above_the_limit(self):
        justification = "x" * (JUSTIFICATION_MAX_LENGTH + 1)

        code = self._error_code(self._payload(justification=justification), "justification")

        self.assertEqual(code, "too_long")

    def test_should_require_the_access_type(self):
        for access_type in (None, "", "  "):
            with self.subTest(access_type=access_type):
                code = self._error_code(self._payload(access_type=access_type), "access_type")

                self.assertEqual(code, "required")

    def test_should_refuse_an_unknown_access_type(self):
        for access_type in ("FOREVER", 1, ["PERMANENT"]):
            with self.subTest(access_type=access_type):
                code = self._error_code(self._payload(access_type=access_type), "access_type")

                self.assertEqual(code, "invalid_choice")

    def test_should_require_the_expiry_of_a_temporary_request(self):
        for expires_on in (None, ""):
            with self.subTest(expires_on=expires_on):
                payload = self._payload(access_type="TEMPORARY", expires_on=expires_on)

                code = self._error_code(payload, "expires_on")

                self.assertEqual(code, "required")

    def test_should_refuse_an_invalid_expiry(self):
        for expires_on in ("03/11/2026", "2026-13-40", 20261103, ["2026-11-03"]):
            with self.subTest(expires_on=expires_on):
                payload = self._payload(access_type="TEMPORARY", expires_on=expires_on)

                code = self._error_code(payload, "expires_on")

                self.assertEqual(code, "invalid")

    def test_should_refuse_an_expiry_in_the_past(self):
        payload = self._payload(access_type="TEMPORARY", expires_on=_yesterday().isoformat())

        code = self._error_code(payload, "expires_on")

        self.assertEqual(code, "in_the_past")

    def test_should_refuse_an_expiry_on_a_permanent_request(self):
        payload = self._payload(expires_on=_tomorrow().isoformat())

        code = self._error_code(payload, "expires_on")

        self.assertEqual(code, "not_allowed")

    def test_should_report_every_invalid_field_at_once(self):
        with self.assertRaises(AccessRequestValidationError) as context:
            validate_access_request_payload({})

        self.assertEqual(sorted(context.exception.errors), ["access_type", "justification"])


class AccessRequestEndpointTestCase(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.other_area = Area.objects.create(acronym="AER", name="Aerodinâmica")
        self.manager = self._user("manager@example.com", self.area)
        self.area.manager = self.manager
        self.area.save(update_fields=["manager"])
        self.other_manager = self._user("other.manager@example.com", self.other_area)
        self.other_area.manager = self.other_manager
        self.other_area.save(update_fields=["manager"])
        self.responsible = self._user("responsible@example.com", self.area)
        self.requester = self._user("requester@example.com", self.other_area)
        self.document = Document.objects.create(
            code="AK-2100-EST-REL-0001",
            title="Relatório da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=DocumentType.objects.create(code="REL", name="Relatório"),
            confidentiality_level="SECRET",
            responsible=self.responsible,
            created_by=self.responsible,
        )
        DocumentArea.objects.create(document=self.document, area=self.area)
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.responsible,
            auditor=self.manager,
            audited_at=timezone.now(),
        )
        self.url = reverse("document-request-access", args=[self.document.pk])
        self.client = Client()
        self.client.force_login(self.requester)

    def _user(self, email, area):
        return User.objects.create_user(
            email=email, password="secret", name=email.split("@")[0], area=area
        )

    def _post(self, body=None, url=None, client=None):
        data = {"justification": VALID_JUSTIFICATION, "access_type": "PERMANENT"}
        if body is not None:
            data = body
        return (client or self.client).post(
            url or self.url, data=json.dumps(data), content_type="application/json"
        )

    def _decide(self, access, status, **fields):
        access.status = status
        access.approver = self.manager
        access.decided_at = timezone.now()
        for name, value in fields.items():
            setattr(access, name, value)
        access.save()


class RequestAccessEndpointTests(AccessRequestEndpointTestCase):
    def test_should_save_a_permanent_request_as_pending(self):
        response = self._post()

        access = DocumentAccess.objects.get(document=self.document, user=self.requester)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            {
                "id": access.pk,
                "document_id": self.document.pk,
                "status": "PENDING",
                "access_type": "PERMANENT",
                "expires_on": None,
                "requested_at": access.requested_at.isoformat(),
            },
        )
        self.assertEqual(access.status, AccessStatus.PENDING)
        self.assertEqual(access.justification, VALID_JUSTIFICATION)
        self.assertIsNone(access.approver)
        self.assertIsNone(access.decided_at)

    def test_should_save_a_temporary_request_with_its_expiry(self):
        expires_on = _tomorrow()

        response = self._post(
            {
                "justification": VALID_JUSTIFICATION,
                "access_type": "TEMPORARY",
                "expires_on": expires_on.isoformat(),
            }
        )

        access = DocumentAccess.objects.get(user=self.requester)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["expires_on"], expires_on.isoformat())
        self.assertEqual(access.access_type, AccessType.TEMPORARY)
        self.assertEqual(access.expires_on, expires_on)

    def test_should_answer_on_the_route_defined_by_the_card(self):
        url = f"/documentos/{self.document.pk}/solicitar-acesso"

        response = self._post(url=url)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "PENDING")

    def test_should_not_grant_access_while_the_request_is_pending(self):
        self._post()

        allowed = can_view_document(self.document, self.requester)

        self.assertFalse(allowed)

    def test_should_write_the_request_to_the_audit_log(self):
        response = self._post()

        entry = AuditLog.objects.get(action=AuditAction.DOC_ACCESS_REQUESTED)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.entity_id, self.document.pk)
        self.assertEqual(entry.user, self.requester)
        self.assertEqual(entry.record["justification"], VALID_JUSTIFICATION)
        self.assertEqual(entry.record["access_type"], "PERMANENT")

    def test_should_answer_400_for_a_missing_justification(self):
        response = self._post({"access_type": "PERMANENT"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["justification"]["code"], "required")
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_answer_400_for_a_blank_justification(self):
        response = self._post({"justification": "    ", "access_type": "PERMANENT"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["justification"]["code"], "required")
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_answer_400_for_a_temporary_request_without_expiry(self):
        response = self._post({"justification": VALID_JUSTIFICATION, "access_type": "TEMPORARY"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["expires_on"]["code"], "required")
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_answer_400_for_a_body_that_is_not_an_object(self):
        response = self._post(["PERMANENT"])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["body"]["code"], "invalid")

    def test_should_answer_400_for_malformed_json(self):
        for body in (b"{not json", b"", b"\xff\xfe"):
            with self.subTest(body=body):
                response = self.client.post(self.url, data=body, content_type="application/json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"error": "InvalidJSON"})

    def test_should_answer_404_for_an_unknown_document(self):
        url = reverse("document-request-access", args=[999999])

        response = self._post(url=url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "DocumentNotFound"})

    def test_should_answer_401_without_a_session(self):
        response = self._post(client=Client())

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_answer_401_for_a_user_id_in_the_body_without_a_session(self):
        response = self._post(
            {
                "user_id": self.requester.pk,
                "justification": VALID_JUSTIFICATION,
                "access_type": "PERMANENT",
            },
            client=Client(),
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_request_for_the_session_user_and_ignore_a_user_id_in_the_body(self):
        response = self._post(
            {
                "user_id": self.other_manager.pk,
                "justification": VALID_JUSTIFICATION,
                "access_type": "PERMANENT",
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(DocumentAccess.objects.filter(user=self.requester).exists())
        self.assertFalse(DocumentAccess.objects.filter(user=self.other_manager).exists())

    def test_should_refuse_a_request_without_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.requester)

        response = self._post(client=client)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_refuse_other_http_methods(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    def test_should_answer_500_without_leaking_details(self):
        with (
            mock.patch(
                "core.views.documents_view.request_document_access",
                side_effect=RuntimeError("host=db password=secret"),
            ),
            self.assertLogs("core.views.documents_view", level="ERROR"),
        ):
            response = self._post()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})


class AccessRequestDuplicationTests(AccessRequestEndpointTestCase):
    def test_should_refuse_a_second_request_while_the_first_is_pending(self):
        first = self._post()

        second = self._post()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            second.json(), {"error": "AccessRequestAlreadyPending", "id": first.json()["id"]}
        )
        self.assertEqual(DocumentAccess.objects.filter(user=self.requester).count(), 1)

    def test_should_keep_the_original_request_when_a_duplicate_is_refused(self):
        self._post()
        original = DocumentAccess.objects.get(user=self.requester)

        self._post(
            {
                "justification": "Outra justificativa com tamanho suficiente.",
                "access_type": "TEMPORARY",
                "expires_on": _tomorrow().isoformat(),
            }
        )

        current = DocumentAccess.objects.get(user=self.requester)
        self.assertEqual(current.justification, VALID_JUSTIFICATION)
        self.assertEqual(current.access_type, AccessType.PERMANENT)
        self.assertEqual(current.requested_at, original.requested_at)

    def test_should_not_audit_a_refused_duplicate(self):
        self._post()

        self._post()

        self.assertEqual(
            AuditLog.objects.filter(action=AuditAction.DOC_ACCESS_REQUESTED).count(), 1
        )

    def test_should_allow_other_users_and_other_documents(self):
        other_user = self._user("colleague@example.com", self.other_area)
        other_client = Client()
        other_client.force_login(other_user)
        other_document = Document.objects.create(
            code="AK-2100-EST-REL-0002",
            title="Relatório da caverna 15",
            project=self.document.project,
            discipline=self.document.discipline,
            document_type=self.document.document_type,
            responsible=self.responsible,
            created_by=self.responsible,
        )
        self._post()

        same_document = self._post(client=other_client)
        same_user = self._post(url=reverse("document-request-access", args=[other_document.pk]))

        self.assertEqual(same_document.status_code, 201)
        self.assertEqual(same_user.status_code, 201)

    def test_should_refuse_a_request_while_a_permanent_grant_is_active(self):
        access = DocumentAccess.objects.create(document=self.document, user=self.requester)
        self._decide(access, AccessStatus.APPROVED)

        response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "AlreadyHasAccess"})
        self.assertEqual(DocumentAccess.objects.get(pk=access.pk).status, AccessStatus.APPROVED)

    def test_should_refuse_a_request_while_a_temporary_grant_is_active(self):
        access = DocumentAccess.objects.create(document=self.document, user=self.requester)
        self._decide(
            access,
            AccessStatus.APPROVED,
            access_type=AccessType.TEMPORARY,
            expires_on=timezone.localdate(),
        )

        response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "AlreadyHasAccess"})

    def test_should_refuse_a_request_from_the_responsible(self):
        client = Client()
        client.force_login(self.responsible)

        response = self._post(client=client)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "AlreadyHasAccess"})
        self.assertFalse(DocumentAccess.objects.exists())

    def test_should_reopen_a_rejected_request_as_pending(self):
        access = DocumentAccess.objects.create(
            document=self.document, user=self.requester, justification="Motivo antigo"
        )
        self._decide(access, AccessStatus.REJECTED)

        response = self._post()

        access.refresh_from_db()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], access.pk)
        self.assertEqual(access.status, AccessStatus.PENDING)
        self.assertEqual(access.justification, VALID_JUSTIFICATION)
        self.assertIsNone(access.approver)
        self.assertIsNone(access.decided_at)
        self.assertIsNotNone(access.requested_at)

    def test_should_reopen_an_expired_grant_as_pending(self):
        access = DocumentAccess.objects.create(document=self.document, user=self.requester)
        self._decide(
            access,
            AccessStatus.APPROVED,
            access_type=AccessType.TEMPORARY,
            expires_on=_yesterday(),
        )

        response = self._post()

        access.refresh_from_db()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(access.status, AccessStatus.PENDING)
        self.assertEqual(access.access_type, AccessType.PERMANENT)
        self.assertIsNone(access.expires_on)

    def test_should_refuse_a_second_request_after_reopening(self):
        access = DocumentAccess.objects.create(document=self.document, user=self.requester)
        self._decide(access, AccessStatus.REJECTED)
        self._post()

        response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "AccessRequestAlreadyPending")

    def test_should_block_a_duplicate_row_at_the_database_level(self):
        DocumentAccess.objects.create(document=self.document, user=self.requester)

        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentAccess.objects.create(document=self.document, user=self.requester)

        self.assertEqual(DocumentAccess.objects.count(), 1)


class AccessRequestModerationQueueTests(AccessRequestEndpointTestCase):
    def test_should_reach_the_queue_of_the_manager_of_the_document_area(self):
        response = self._post()

        queue = pending_access_requests(self.manager)
        self.assertEqual([access.pk for access in queue], [response.json()["id"]])

    def test_should_not_reach_the_queue_of_a_manager_of_another_area(self):
        self._post()

        queue = pending_access_requests(self.other_manager)

        self.assertEqual(list(queue), [])

    def test_should_show_the_requested_terms_in_the_manager_panel(self):
        expires_on = _tomorrow()
        self._post(
            {
                "justification": VALID_JUSTIFICATION,
                "access_type": "TEMPORARY",
                "expires_on": expires_on.isoformat(),
            }
        )
        manager_client = Client()
        manager_client.force_login(self.manager)

        response = manager_client.get(reverse("manager-pending-access-requests"))

        result = response.json()["results"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["justification"], VALID_JUSTIFICATION)
        self.assertEqual(result["access_type"], "TEMPORARY")
        self.assertEqual(result["expires_on"], expires_on.isoformat())

    def test_should_grant_access_when_the_manager_approves_the_request(self):
        access_id = self._post().json()["id"]
        manager_client = Client()
        manager_client.force_login(self.manager)

        response = manager_client.post(
            reverse("manager-access-request-decision", args=[access_id]),
            data=json.dumps({"decision": "APPROVED"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["access_type"], "PERMANENT")
        self.assertTrue(can_view_document(self.document, self.requester))


class TemporaryGrantTests(AccessRequestEndpointTestCase):
    def _grant(self, expires_on):
        access = DocumentAccess.objects.create(document=self.document, user=self.requester)
        self._decide(
            access,
            AccessStatus.APPROVED,
            access_type=AccessType.TEMPORARY,
            expires_on=expires_on,
        )
        return access

    def test_should_allow_reading_through_the_last_day_of_the_grant(self):
        self._grant(timezone.localdate())

        allowed = can_view_document(self.document, self.requester)

        self.assertTrue(allowed)

    def test_should_stop_allowing_reading_after_the_grant_expires(self):
        self._grant(_yesterday())

        allowed = can_view_document(self.document, self.requester)

        self.assertFalse(allowed)

    def test_should_hide_the_description_after_the_grant_expires(self):
        self._grant(_yesterday())

        response = self.client.get(reverse("document-detail", args=[self.document.pk]))

        body = response.json()
        self.assertNotIn("description", body)
        self.assertEqual(body["access_status"], "PENDING")
        self.assertEqual(body["access_request"]["expires_on"], _yesterday().isoformat())

    def test_should_refuse_a_temporary_row_without_expiry_at_the_database_level(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentAccess.objects.create(
                document=self.document,
                user=self.requester,
                access_type=AccessType.TEMPORARY,
            )

    def test_should_refuse_a_permanent_row_with_expiry_at_the_database_level(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentAccess.objects.create(
                document=self.document,
                user=self.requester,
                expires_on=_tomorrow(),
            )
