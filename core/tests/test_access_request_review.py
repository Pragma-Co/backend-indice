import json
from datetime import timedelta
from unittest import mock

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
    Role,
    User,
)
from core.services.access_request_exceptions import (
    AccessRequestAlreadyDecidedError,
    AccessRequestExpiredError,
    AccessRequestNotFoundError,
    AccessRequestValidationError,
    OwnAccessRequestReviewError,
)
from core.services.access_request_service import (
    decide_access_request,
    get_access_request_detail,
    is_access_approver,
    pending_access_requests,
    validate_decision_payload,
)
from core.services.documents_service import can_view_document

OPINION = "Parecer técnico para esta solicitação."
APPROVAL = {"decision": "APPROVED", "opinion": OPINION}
REJECTION = {"decision": "REJECTED", "opinion": OPINION}


class AccessRequestFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.other_area = Area.objects.create(acronym="AER", name="Aerodinâmica")
        self.manager = self._user("manager@example.com", self.area, Role.AUDITOR)
        self.area.manager = self.manager
        self.area.save(update_fields=["manager"])
        self.other_manager = self._user("other.manager@example.com", self.other_area, Role.ADMIN)
        self.other_area.manager = self.other_manager
        self.other_area.save(update_fields=["manager"])
        self.responsible = self._user("responsible@example.com", self.area, Role.AUTHOR)
        self.requester = self._user("requester@example.com", self.other_area)
        self.outsider = self._user("outsider@example.com", self.other_area)

        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="REL", name="Relatório")
        self.document = self._document("AK-2100-EST-REL-0001", self.area)
        self.other_document = self._document("AK-2100-EST-REL-0002", self.other_area)
        self.request = self._access(self.document, self.requester, days_ago=2)

    def _user(self, email, area, role=Role.VIEWER):
        return User.objects.create_user(
            email=email, password="secret", name=email.split("@")[0], area=area, role=role
        )

    def _document(self, code, area):
        document = Document.objects.create(
            code=code,
            title=f"Relatório {code}",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            confidentiality_level="CONFIDENTIAL",
            responsible=self.responsible,
            created_by=self.responsible,
        )
        DocumentArea.objects.create(document=document, area=area)
        return document

    def _archive(self, document):
        document.archived_at = timezone.now()
        document.archived_by = self.manager
        document.save(update_fields=["archived_at", "archived_by"])

    def _make_temporary(self, access, expires_on):
        access.access_type = AccessType.TEMPORARY
        access.expires_on = expires_on
        access.save(update_fields=["access_type", "expires_on"])

    def _access(self, document, user, days_ago=1):
        return DocumentAccess.objects.create(
            document=document,
            user=user,
            status=AccessStatus.PENDING,
            justification="Preciso do relatório para o plano de inspeção.",
            requested_at=timezone.now() - timedelta(days=days_ago),
        )


class IsAccessApproverTests(AccessRequestFixtureMixin, TestCase):
    def test_should_accept_the_manager_of_an_active_area(self):
        result = is_access_approver(self.manager)

        self.assertTrue(result)

    def test_should_refuse_the_responsible_without_a_manager_role(self):
        result = is_access_approver(self.responsible)

        self.assertFalse(result)

    def test_should_refuse_a_user_without_managed_areas_or_documents(self):
        result = is_access_approver(self.outsider)

        self.assertFalse(result)

    def test_should_accept_a_manager_even_when_their_area_is_inactive(self):
        self.other_area.active = False
        self.other_area.save(update_fields=["active"])

        result = is_access_approver(self.other_manager)

        self.assertTrue(result)

    def test_should_refuse_an_inactive_manager(self):
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])

        result = is_access_approver(self.manager)

        self.assertFalse(result)


class PendingAccessRequestsServiceTests(AccessRequestFixtureMixin, TestCase):
    def test_should_list_pending_requests_of_documents_in_all_areas(self):
        other_request = self._access(self.other_document, self.outsider)
        decided = self._access(self.document, self.outsider)
        decided.status = AccessStatus.REJECTED
        decided.approver = self.manager
        decided.decided_at = timezone.now()
        decided.save()

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [self.request, other_request])

    def test_should_not_list_requests_for_a_responsible_without_a_manager_role(self):
        self._access(self.other_document, self.outsider, days_ago=1)

        result = list(pending_access_requests(self.responsible))

        self.assertEqual(result, [])

    def test_should_not_list_the_approver_own_request(self):
        self._access(self.document, self.manager)

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [self.request])

    def test_should_list_requests_even_if_the_document_area_is_inactive(self):
        self.area.active = False
        self.area.save(update_fields=["active"])

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [self.request])

    def test_should_not_list_requests_of_archived_document_types(self):
        self.document_type.active = False
        self.document_type.save(update_fields=["active"])

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [])

    def test_should_not_list_requests_of_archived_documents(self):
        self._archive(self.document)

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [])


class AccessRequestDetailServiceTests(AccessRequestFixtureMixin, TestCase):
    def test_should_return_a_pending_request_of_a_managed_document(self):
        access = get_access_request_detail(self.request.pk, self.manager)

        self.assertEqual(access, self.request)

    def test_should_return_a_request_that_was_already_decided(self):
        decide_access_request(self.request.pk, self.manager, REJECTION)

        access = get_access_request_detail(self.request.pk, self.other_manager)

        self.assertEqual(access.status, AccessStatus.REJECTED)
        self.assertEqual(access.approver, self.manager)

    def test_should_show_requests_to_managers_from_other_areas(self):
        access = get_access_request_detail(self.request.pk, self.other_manager)

        self.assertEqual(access, self.request)

    def test_should_hide_requests_from_the_responsible_without_a_manager_role(self):
        with self.assertRaises(AccessRequestNotFoundError):
            get_access_request_detail(self.request.pk, self.responsible)

    def test_should_hide_the_approver_own_request(self):
        own_request = self._access(self.document, self.manager)

        with self.assertRaises(AccessRequestNotFoundError):
            get_access_request_detail(own_request.pk, self.manager)

    def test_should_hide_requests_of_archived_documents(self):
        self._archive(self.document)

        with self.assertRaises(AccessRequestNotFoundError):
            get_access_request_detail(self.request.pk, self.manager)

    def test_should_refuse_an_unknown_request(self):
        with self.assertRaises(AccessRequestNotFoundError):
            get_access_request_detail(999999, self.manager)


class DecideAccessRequestServiceTests(AccessRequestFixtureMixin, TestCase):
    def test_should_approve_the_request_and_grant_access_to_the_requester(self):
        access = decide_access_request(
            self.request.pk, self.manager, {**APPROVAL, "decision": "approved"}
        )

        self.assertEqual(access.status, AccessStatus.APPROVED)
        self.assertEqual(access.approver, self.manager)
        self.assertIsNotNone(access.decided_at)
        self.assertTrue(can_view_document(self.document, self.requester))

    def test_should_reject_the_request_without_granting_access(self):
        access = decide_access_request(self.request.pk, self.manager, REJECTION)

        self.assertEqual(access.status, AccessStatus.REJECTED)
        self.assertFalse(can_view_document(self.document, self.requester))

    def test_should_not_let_the_responsible_without_a_manager_role_decide(self):
        with self.assertRaises(AccessRequestNotFoundError):
            decide_access_request(self.request.pk, self.responsible, APPROVAL)

        self.request.refresh_from_db()
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_let_a_manager_from_another_area_decide(self):
        access = decide_access_request(self.request.pk, self.other_manager, APPROVAL)

        self.assertEqual(access.approver, self.other_manager)
        self.assertTrue(can_view_document(self.document, self.requester))

    def test_should_refuse_an_unknown_request(self):
        with self.assertRaises(AccessRequestNotFoundError):
            decide_access_request(999999, self.manager, APPROVAL)

    def test_should_refuse_a_request_that_was_already_decided(self):
        decide_access_request(self.request.pk, self.manager, REJECTION)

        with self.assertRaises(AccessRequestAlreadyDecidedError) as context:
            decide_access_request(self.request.pk, self.manager, APPROVAL)

        self.assertEqual(context.exception.status, AccessStatus.REJECTED)

    def test_should_refuse_the_approver_deciding_their_own_request(self):
        own_request = self._access(self.document, self.manager)

        with self.assertRaises(OwnAccessRequestReviewError):
            decide_access_request(own_request.pk, self.manager, APPROVAL)

        own_request.refresh_from_db()
        self.assertEqual(own_request.status, AccessStatus.PENDING)

    def test_should_refuse_a_missing_decision(self):
        with self.assertRaises(AccessRequestValidationError) as context:
            decide_access_request(self.request.pk, self.manager, {})

        self.assertEqual(context.exception.errors["decision"]["code"], "required")

    def test_should_refuse_a_decision_outside_the_allowed_choices(self):
        with self.assertRaises(AccessRequestValidationError) as context:
            decide_access_request(self.request.pk, self.manager, {"decision": "PENDING"})

        self.assertEqual(context.exception.errors["decision"]["code"], "invalid_choice")

    def test_should_refuse_a_payload_that_is_not_an_object(self):
        with self.assertRaises(AccessRequestValidationError) as context:
            decide_access_request(self.request.pk, self.manager, ["APPROVED"])

        self.assertIn("body", context.exception.errors)

    def test_should_refuse_approving_a_temporary_request_that_already_expired(self):
        expired_on = timezone.localdate() - timedelta(days=1)
        self._make_temporary(self.request, expired_on)

        with self.assertRaises(AccessRequestExpiredError) as context:
            decide_access_request(self.request.pk, self.manager, APPROVAL)

        self.request.refresh_from_db()
        self.assertEqual(context.exception.expires_on, expired_on)
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_reject_a_temporary_request_that_already_expired(self):
        self._make_temporary(self.request, timezone.localdate() - timedelta(days=1))

        access = decide_access_request(self.request.pk, self.manager, REJECTION)

        self.assertEqual(access.status, AccessStatus.REJECTED)

    def test_should_approve_a_temporary_request_expiring_today(self):
        self._make_temporary(self.request, timezone.localdate())

        access = decide_access_request(self.request.pk, self.manager, APPROVAL)

        self.assertEqual(access.status, AccessStatus.APPROVED)
        self.assertTrue(can_view_document(self.document, self.requester))

    def test_should_refuse_deciding_a_request_of_an_archived_document(self):
        self._archive(self.document)

        with self.assertRaises(AccessRequestNotFoundError):
            decide_access_request(self.request.pk, self.manager, APPROVAL)


class PendingAccessRequestsViewTests(AccessRequestFixtureMixin, TestCase):
    def test_should_return_the_paginated_pending_queue(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager-pending-access-requests"))

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["current_page"], 1)
        self.assertEqual(body["results"][0]["id"], self.request.pk)
        self.assertEqual(body["results"][0]["document"]["code"], self.document.code)
        self.assertEqual(body["results"][0]["requester"]["area"]["acronym"], "AER")
        self.assertNotIn("email", body["results"][0]["requester"])

    def test_should_require_authentication(self):
        response = self.client.get(reverse("manager-pending-access-requests"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})

    def test_should_forbid_users_who_cannot_decide_access_requests(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("manager-pending-access-requests"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "PermissionDenied"})

    def test_should_reject_invalid_pagination(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("manager-pending-access-requests"), {"page": "0", "page_size": "500"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"page", "page_size"})

    def test_should_reject_methods_other_than_get(self):
        self.client.force_login(self.manager)

        response = self.client.post(reverse("manager-pending-access-requests"))

        self.assertEqual(response.status_code, 405)


class AccessRequestDetailViewTests(AccessRequestFixtureMixin, TestCase):
    def _get(self, access_id):
        return self.client.get(reverse("manager-access-request-detail", args=[access_id]))

    def test_should_return_the_details_of_a_pending_request(self):
        self.client.force_login(self.manager)

        response = self._get(self.request.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.request.pk,
                "status": "PENDING",
                "justification": "Preciso do relatório para o plano de inspeção.",
                "access_type": "PERMANENT",
                "expires_on": None,
                "requested_at": self.request.requested_at.isoformat(),
                "requester": {
                    "id": self.requester.pk,
                    "name": "requester",
                    "area": {"acronym": "AER", "name": "Aerodinâmica"},
                },
                "document": {
                    "id": self.document.pk,
                    "code": "AK-2100-EST-REL-0001",
                    "title": "Relatório AK-2100-EST-REL-0001",
                    "confidentiality_level": "CONFIDENTIAL",
                    "project": {"code": "AK-2100", "name": "Fuselagem"},
                    "discipline": {"code": "EST", "name": "Estruturas"},
                    "document_type": {"code": "REL", "name": "Relatório"},
                    "responsible": {"id": self.responsible.pk, "name": "responsible"},
                    "areas": [{"acronym": "EST", "name": "Engenharia Estrutural"}],
                },
                "approver": None,
                "decided_at": None,
                "decision_opinion": "",
            },
        )

    def test_should_return_the_decision_of_a_decided_request(self):
        self.client.force_login(self.manager)
        access = decide_access_request(self.request.pk, self.manager, APPROVAL)

        response = self._get(self.request.pk)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "APPROVED")
        self.assertEqual(body["approver"], {"id": self.manager.pk, "name": "manager"})
        self.assertEqual(body["decided_at"], access.decided_at.isoformat())

    def test_should_not_expose_the_requester_email(self):
        self.client.force_login(self.manager)

        response = self._get(self.request.pk)

        self.assertNotIn("email", response.json()["requester"])

    def test_should_require_authentication(self):
        response = self._get(self.request.pk)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})

    def test_should_forbid_users_who_cannot_decide_access_requests(self):
        self.client.force_login(self.requester)

        response = self._get(self.request.pk)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "PermissionDenied"})

    def test_should_allow_a_manager_from_another_area(self):
        self.client.force_login(self.other_manager)

        response = self._get(self.request.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.request.pk)

    def test_should_forbid_the_responsible_without_a_manager_role(self):
        self.client.force_login(self.responsible)

        response = self._get(self.request.pk)

        self.assertEqual(response.status_code, 403)

    def test_should_answer_not_found_for_an_unknown_request(self):
        self.client.force_login(self.manager)

        response = self._get(999999)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "AccessRequestNotFound"})

    def test_should_reject_methods_other_than_get(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("manager-access-request-detail", args=[self.request.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_should_answer_500_without_leaking_details(self):
        self.client.force_login(self.manager)

        with (
            mock.patch(
                "core.views.access_request_view.get_access_request_detail",
                side_effect=RuntimeError("password=secret host=db"),
            ),
            self.assertLogs("core.views.access_request_view", level="ERROR"),
        ):
            response = self._get(self.request.pk)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})


class AccessRequestDecisionViewTests(AccessRequestFixtureMixin, TestCase):
    def _post(self, access_id, payload, client=None):
        return (client or self.client).post(
            reverse("manager-access-request-decision", args=[access_id]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_should_approve_the_request_and_write_an_audit_entry(self):
        self.client.force_login(self.manager)

        response = self._post(self.request.pk, APPROVAL)

        body = response.json()
        audit = AuditLog.objects.get(entity="document_access", entity_id=self.request.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], AccessStatus.APPROVED)
        self.assertEqual(body["decision_opinion"], OPINION)
        self.assertEqual(body["approver"]["id"], self.manager.pk)
        self.assertEqual(body["requester"]["id"], self.requester.pk)
        self.assertEqual(audit.action, AuditAction.UPDATE)
        self.assertEqual(audit.user, self.manager)
        self.assertEqual(audit.record["event"], "ACCESS_APPROVED")
        self.assertEqual(audit.record["opinion"], OPINION)

    def test_should_require_a_valid_opinion_for_both_decisions(self):
        self.client.force_login(self.manager)
        for decision in ("APPROVED", "REJECTED"):
            for opinion in (None, "", "x" * 19, "x" * 1001, 42):
                with self.subTest(decision=decision, opinion=opinion):
                    response = self._post(
                        self.request.pk, {"decision": decision, "opinion": opinion}
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("opinion", response.json()["errors"])
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_accept_trimmed_opinion_at_both_limits(self):
        for decision in ("APPROVED", "REJECTED"):
            for length in (20, 1000):
                with self.subTest(decision=decision, length=length):
                    payload = {"decision": decision, "opinion": f" {'x' * length} "}
                    self.assertEqual(validate_decision_payload(payload)["opinion"], "x" * length)

    def test_should_require_authentication(self):
        response = self._post(self.request.pk, APPROVAL)

        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_forbid_users_who_cannot_decide_access_requests(self):
        self.client.force_login(self.requester)

        response = self._post(self.request.pk, APPROVAL)

        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_allow_a_manager_from_another_area(self):
        self.client.force_login(self.other_manager)

        response = self._post(self.request.pk, APPROVAL)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(can_view_document(self.document, self.requester))

    def test_should_forbid_the_responsible_without_a_manager_role(self):
        self.client.force_login(self.responsible)

        response = self._post(self.request.pk, APPROVAL)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(can_view_document(self.document, self.requester))

    def test_should_forbid_deciding_an_own_request(self):
        own_request = self._access(self.document, self.manager)
        self.client.force_login(self.manager)

        response = self._post(own_request.pk, APPROVAL)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "CannotReviewOwnAccessRequest"})

    def test_should_answer_conflict_for_a_request_already_decided(self):
        self.client.force_login(self.manager)
        self._post(self.request.pk, REJECTION)

        response = self._post(self.request.pk, APPROVAL)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"error": "AccessRequestAlreadyDecided", "status": "REJECTED"}
        )

    def test_should_reject_an_invalid_decision(self):
        self.client.force_login(self.manager)

        response = self._post(self.request.pk, {"decision": "MAYBE"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["decision"]["code"], "invalid_choice")

    def test_should_answer_conflict_for_approving_an_expired_temporary_request(self):
        expired_on = timezone.localdate() - timedelta(days=1)
        self._make_temporary(self.request, expired_on)
        self.client.force_login(self.manager)

        response = self._post(self.request.pk, APPROVAL)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"error": "AccessRequestExpired", "expires_on": expired_on.isoformat()},
        )
        self.assertFalse(AuditLog.objects.filter(entity="document_access").exists())

    def test_should_reject_a_malformed_json_body(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("manager-access-request-decision", args=[self.request.pk]),
            data="{decision",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "InvalidJSON"})

    def test_should_reject_methods_other_than_post(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("manager-access-request-decision", args=[self.request.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_should_reject_a_decision_without_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)

        response = self._post(
            self.request.pk,
            APPROVAL,
            client=client,
        )

        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessStatus.PENDING)
