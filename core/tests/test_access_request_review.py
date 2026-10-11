import json
from datetime import timedelta

from django.test import Client, TestCase
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
    Project,
    Role,
    User,
)
from core.services.access_request_exceptions import (
    AccessRequestAlreadyDecidedError,
    AccessRequestNotFoundError,
    AccessRequestValidationError,
    OwnAccessRequestReviewError,
)
from core.services.access_request_service import (
    decide_access_request,
    is_access_approver,
    pending_access_requests,
)
from core.services.documents_service import can_view_document


class AccessRequestFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.other_area = Area.objects.create(acronym="AER", name="Aerodinâmica")
        self.manager = self._user("manager@example.com", self.area)
        self.area.manager = self.manager
        self.area.save(update_fields=["manager"])
        self.other_manager = self._user("other.manager@example.com", self.other_area)
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

    def test_should_accept_the_responsible_for_a_document(self):
        result = is_access_approver(self.responsible)

        self.assertTrue(result)

    def test_should_refuse_a_user_without_managed_areas_or_documents(self):
        result = is_access_approver(self.outsider)

        self.assertFalse(result)

    def test_should_refuse_the_manager_of_an_inactive_area(self):
        self.other_area.active = False
        self.other_area.save(update_fields=["active"])

        result = is_access_approver(self.other_manager)

        self.assertFalse(result)

    def test_should_refuse_an_inactive_manager(self):
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])

        result = is_access_approver(self.manager)

        self.assertFalse(result)


class PendingAccessRequestsServiceTests(AccessRequestFixtureMixin, TestCase):
    def test_should_list_only_pending_requests_of_documents_in_the_managed_areas(self):
        self._access(self.other_document, self.outsider)
        decided = self._access(self.document, self.outsider)
        decided.status = AccessStatus.REJECTED
        decided.approver = self.manager
        decided.decided_at = timezone.now()
        decided.save()

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [self.request])

    def test_should_list_requests_of_documents_the_user_is_responsible_for(self):
        other_request = self._access(self.other_document, self.outsider, days_ago=1)

        result = list(pending_access_requests(self.responsible))

        self.assertEqual(result, [self.request, other_request])

    def test_should_not_list_the_approver_own_request(self):
        self._access(self.document, self.manager)

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [self.request])

    def test_should_not_list_requests_of_inactive_areas(self):
        self.area.active = False
        self.area.save(update_fields=["active"])

        result = list(pending_access_requests(self.manager))

        self.assertEqual(result, [])

    def test_should_not_list_requests_of_archived_document_types(self):
        self.document_type.active = False
        self.document_type.save(update_fields=["active"])

        result = list(pending_access_requests(self.responsible))

        self.assertEqual(result, [])


class DecideAccessRequestServiceTests(AccessRequestFixtureMixin, TestCase):
    def test_should_approve_the_request_and_grant_access_to_the_requester(self):
        access = decide_access_request(self.request.pk, self.manager, {"decision": "approved"})

        self.assertEqual(access.status, AccessStatus.APPROVED)
        self.assertEqual(access.approver, self.manager)
        self.assertIsNotNone(access.decided_at)
        self.assertTrue(can_view_document(self.document, self.requester))

    def test_should_reject_the_request_without_granting_access(self):
        access = decide_access_request(self.request.pk, self.manager, {"decision": "REJECTED"})

        self.assertEqual(access.status, AccessStatus.REJECTED)
        self.assertFalse(can_view_document(self.document, self.requester))

    def test_should_let_the_responsible_decide(self):
        access = decide_access_request(self.request.pk, self.responsible, {"decision": "APPROVED"})

        self.assertEqual(access.approver, self.responsible)

    def test_should_hide_requests_of_documents_outside_the_approver_scope(self):
        with self.assertRaises(AccessRequestNotFoundError):
            decide_access_request(self.request.pk, self.other_manager, {"decision": "APPROVED"})

        self.request.refresh_from_db()
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_refuse_an_unknown_request(self):
        with self.assertRaises(AccessRequestNotFoundError):
            decide_access_request(999999, self.manager, {"decision": "APPROVED"})

    def test_should_refuse_a_request_that_was_already_decided(self):
        decide_access_request(self.request.pk, self.manager, {"decision": "REJECTED"})

        with self.assertRaises(AccessRequestAlreadyDecidedError) as context:
            decide_access_request(self.request.pk, self.manager, {"decision": "APPROVED"})

        self.assertEqual(context.exception.status, AccessStatus.REJECTED)

    def test_should_refuse_the_approver_deciding_their_own_request(self):
        own_request = self._access(self.document, self.manager)

        with self.assertRaises(OwnAccessRequestReviewError):
            decide_access_request(own_request.pk, self.manager, {"decision": "APPROVED"})

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


class AccessRequestDecisionViewTests(AccessRequestFixtureMixin, TestCase):
    def _post(self, access_id, payload, client=None):
        return (client or self.client).post(
            reverse("manager-access-request-decision", args=[access_id]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_should_approve_the_request_and_write_an_audit_entry(self):
        self.client.force_login(self.manager)

        response = self._post(self.request.pk, {"decision": "APPROVED"})

        body = response.json()
        audit = AuditLog.objects.get(entity="document_access", entity_id=self.request.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], AccessStatus.APPROVED)
        self.assertEqual(body["approver"]["id"], self.manager.pk)
        self.assertEqual(body["requester"]["id"], self.requester.pk)
        self.assertEqual(audit.action, AuditAction.UPDATE)
        self.assertEqual(audit.user, self.manager)
        self.assertEqual(audit.record["event"], "ACCESS_APPROVED")

    def test_should_require_authentication(self):
        response = self._post(self.request.pk, {"decision": "APPROVED"})

        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_forbid_users_who_cannot_decide_access_requests(self):
        self.client.force_login(self.requester)

        response = self._post(self.request.pk, {"decision": "APPROVED"})

        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessStatus.PENDING)

    def test_should_answer_not_found_for_a_request_outside_the_approver_scope(self):
        self.client.force_login(self.other_manager)

        response = self._post(self.request.pk, {"decision": "APPROVED"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "AccessRequestNotFound"})

    def test_should_forbid_deciding_an_own_request(self):
        own_request = self._access(self.document, self.manager)
        self.client.force_login(self.manager)

        response = self._post(own_request.pk, {"decision": "APPROVED"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "CannotReviewOwnAccessRequest"})

    def test_should_answer_conflict_for_a_request_already_decided(self):
        self.client.force_login(self.manager)
        self._post(self.request.pk, {"decision": "REJECTED"})

        response = self._post(self.request.pk, {"decision": "APPROVED"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"error": "AccessRequestAlreadyDecided", "status": "REJECTED"}
        )

    def test_should_reject_an_invalid_decision(self):
        self.client.force_login(self.manager)

        response = self._post(self.request.pk, {"decision": "MAYBE"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["decision"]["code"], "invalid_choice")

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

        response = self._post(self.request.pk, {"decision": "APPROVED"}, client=client)

        self.request.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request.status, AccessStatus.PENDING)
