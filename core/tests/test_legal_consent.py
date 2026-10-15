import json
from unittest import mock

from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    LegalClause,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentVersion,
    User,
    UserClauseConsent,
    UserLegalAcceptance,
)
from core.services.legal_consent_exceptions import (
    LegalConsentValidationError,
    LegalDocumentNotFoundError,
    LegalVersionAlreadyAcceptedError,
    LegalVersionNotFoundError,
    OutdatedLegalVersionError,
)
from core.services.legal_consent_service import (
    current_legal_version,
    record_acceptance,
    user_acceptances,
)


class LegalConsentFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = self._user("titular@example.com")
        self.other_user = self._user("outro.titular@example.com")
        self.document = LegalDocument.objects.create(
            slug="termo-tratamento-dados", title="Termo de Tratamento de Dados"
        )
        self.version = self._version(1, LegalDocumentStatus.PUBLISHED)
        self.required_clause = self._clause(self.version, "objeto", 1, is_required=True)
        self.optional_clause = self._clause(self.version, "comunicados", 2, is_required=False)

    def _user(self, email):
        return User.objects.create_user(
            email=email, password="secret", name=email.split("@")[0], area=self.area
        )

    def _version(self, number, status):
        return LegalDocumentVersion.objects.create(
            document=self.document,
            version=number,
            status=status,
            summary="Declaração do Titular.",
            content_hash="a" * 64,
            created_by=self.user,
            published_at=None if status == LegalDocumentStatus.DRAFT else timezone.now(),
        )

    def _clause(self, version, code, position, is_required):
        return LegalClause.objects.create(
            version=version,
            code=code,
            position=position,
            title=f"Artigo {position}",
            body=f"Texto da cláusula {code}.",
            is_required=is_required,
        )

    def _payload(self, optional_accepted=False, version=None):
        return {
            "version_id": (version or self.version).pk,
            "consents": [
                {"clause_id": self.required_clause.pk, "accepted": True},
                {"clause_id": self.optional_clause.pk, "accepted": optional_accepted},
            ],
        }


class CurrentLegalVersionServiceTests(LegalConsentFixtureMixin, TestCase):
    def test_should_return_the_highest_published_version_with_ordered_clauses(self):
        self._version(2, LegalDocumentStatus.DRAFT)

        version = current_legal_version(self.document.slug)

        self.assertEqual(version, self.version)
        self.assertEqual(
            [clause.code for clause in version.clauses.all()], ["objeto", "comunicados"]
        )

    def test_should_refuse_a_document_without_published_versions(self):
        self.version.status = LegalDocumentStatus.DRAFT
        self.version.published_at = None
        self.version.save(update_fields=["status", "published_at"])

        with self.assertRaises(LegalDocumentNotFoundError):
            current_legal_version(self.document.slug)

    def test_should_refuse_an_unknown_document(self):
        with self.assertRaises(LegalDocumentNotFoundError):
            current_legal_version("termo-inexistente")


class RecordAcceptanceServiceTests(LegalConsentFixtureMixin, TestCase):
    def test_should_record_the_decision_of_each_clause(self):
        acceptance = record_acceptance(
            self.user, self._payload(), ip_address="10.0.0.1", user_agent="Mozilla/5.0"
        )

        decisions = dict(
            UserClauseConsent.objects.filter(acceptance=acceptance).values_list(
                "clause_id", "accepted"
            )
        )
        self.assertEqual(decisions, {self.required_clause.pk: True, self.optional_clause.pk: False})
        self.assertEqual(acceptance.user, self.user)
        self.assertEqual(acceptance.version, self.version)
        self.assertEqual(acceptance.ip_address, "10.0.0.1")
        self.assertEqual(acceptance.user_agent, "Mozilla/5.0")
        self.assertIsNotNone(acceptance.accepted_at)

    def test_should_mark_the_user_as_having_accepted_the_terms(self):
        acceptance = record_acceptance(self.user, self._payload())

        self.user.refresh_from_db()
        self.assertEqual(self.user.terms_accepted_at, acceptance.accepted_at)

    def test_should_truncate_a_long_user_agent(self):
        acceptance = record_acceptance(self.user, self._payload(), user_agent="x" * 900)

        self.assertEqual(len(acceptance.user_agent), 500)

    def test_should_refuse_declining_a_required_clause(self):
        payload = self._payload()
        payload["consents"][0]["accepted"] = False

        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, payload)

        error = context.exception.errors["consents"]
        self.assertEqual(error["code"], "required_clause_declined")
        self.assertEqual(error["clause_ids"], [self.required_clause.pk])
        self.assertFalse(UserLegalAcceptance.objects.exists())

    def test_should_refuse_a_clause_left_unanswered(self):
        payload = self._payload()
        payload["consents"].pop()

        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, payload)

        error = context.exception.errors["consents"]
        self.assertEqual(error["code"], "missing_clauses")
        self.assertEqual(error["clause_ids"], [self.optional_clause.pk])
        self.assertFalse(UserLegalAcceptance.objects.exists())

    def test_should_refuse_a_clause_of_another_version(self):
        draft = self._version(2, LegalDocumentStatus.DRAFT)
        foreign_clause = self._clause(draft, "objeto", 1, is_required=True)
        payload = self._payload()
        payload["consents"].append({"clause_id": foreign_clause.pk, "accepted": True})

        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, payload)

        error = context.exception.errors["consents"]
        self.assertEqual(error["code"], "unknown_clauses")
        self.assertEqual(error["clause_ids"], [foreign_clause.pk])

    def test_should_refuse_a_clause_answered_twice(self):
        payload = self._payload()
        payload["consents"].append({"clause_id": self.optional_clause.pk, "accepted": True})

        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, payload)

        self.assertEqual(context.exception.errors["consents[2]"]["code"], "duplicate")

    def test_should_refuse_values_with_wrong_types(self):
        payload = {
            "version_id": True,
            "consents": [
                {"clause_id": str(self.required_clause.pk), "accepted": True},
                {"clause_id": self.optional_clause.pk, "accepted": "false"},
                "objeto",
            ],
        }

        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, payload)

        self.assertEqual(
            set(context.exception.errors),
            {"version_id", "consents[0]", "consents[1]", "consents[2]"},
        )

    def test_should_refuse_missing_required_fields(self):
        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, {})

        self.assertEqual(context.exception.errors["version_id"]["code"], "required")
        self.assertEqual(context.exception.errors["consents"]["code"], "required")

    def test_should_refuse_too_many_consents(self):
        payload = {
            "version_id": self.version.pk,
            "consents": [{"clause_id": index, "accepted": True} for index in range(1, 202)],
        }

        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, payload)

        self.assertEqual(context.exception.errors["consents"]["code"], "too_long")

    def test_should_refuse_a_payload_that_is_not_an_object(self):
        with self.assertRaises(LegalConsentValidationError) as context:
            record_acceptance(self.user, [self.version.pk])

        self.assertIn("body", context.exception.errors)

    def test_should_refuse_an_unpublished_version(self):
        draft = self._version(2, LegalDocumentStatus.DRAFT)

        with self.assertRaises(LegalVersionNotFoundError):
            record_acceptance(self.user, {"version_id": draft.pk, "consents": []})

    def test_should_refuse_an_unknown_version(self):
        with self.assertRaises(LegalVersionNotFoundError):
            record_acceptance(self.user, {"version_id": 999999, "consents": []})

    def test_should_refuse_a_version_superseded_by_a_newer_publication(self):
        newer = self._version(2, LegalDocumentStatus.PUBLISHED)

        with self.assertRaises(OutdatedLegalVersionError) as context:
            record_acceptance(self.user, self._payload())

        self.assertEqual(context.exception.current_version_id, newer.pk)
        self.assertFalse(UserLegalAcceptance.objects.exists())

    def test_should_refuse_accepting_the_same_version_twice(self):
        record_acceptance(self.user, self._payload(optional_accepted=False))

        with self.assertRaises(LegalVersionAlreadyAcceptedError):
            record_acceptance(self.user, self._payload(optional_accepted=True))

        self.assertFalse(UserClauseConsent.objects.get(clause=self.optional_clause).accepted)

    def test_should_let_another_user_accept_the_same_version(self):
        record_acceptance(self.user, self._payload())

        acceptance = record_acceptance(self.other_user, self._payload())

        self.assertEqual(acceptance.user, self.other_user)


class UserAcceptancesServiceTests(LegalConsentFixtureMixin, TestCase):
    def test_should_list_only_the_user_acceptances_newest_first(self):
        first = record_acceptance(self.user, self._payload())
        record_acceptance(self.other_user, self._payload())
        newer = self._version(2, LegalDocumentStatus.PUBLISHED)
        newer_clause = self._clause(newer, "objeto", 1, is_required=True)
        second = record_acceptance(
            self.user,
            {
                "version_id": newer.pk,
                "consents": [{"clause_id": newer_clause.pk, "accepted": True}],
            },
        )

        result = list(user_acceptances(self.user))

        self.assertEqual(result, [second, first])


class CurrentLegalVersionViewTests(LegalConsentFixtureMixin, TestCase):
    def test_should_return_the_current_version_with_its_clauses(self):
        response = self.client.get(reverse("legal-document-current", args=[self.document.slug]))

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["id"], self.version.pk)
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["document"]["slug"], self.document.slug)
        self.assertEqual(
            [(clause["id"], clause["is_required"]) for clause in body["clauses"]],
            [(self.required_clause.pk, True), (self.optional_clause.pk, False)],
        )

    def test_should_answer_not_found_for_an_unknown_document(self):
        response = self.client.get(reverse("legal-document-current", args=["termo-inexistente"]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "LegalDocumentNotFound"})

    def test_should_reject_methods_other_than_get(self):
        response = self.client.post(reverse("legal-document-current", args=[self.document.slug]))

        self.assertEqual(response.status_code, 405)


class LegalAcceptancesViewTests(LegalConsentFixtureMixin, TestCase):
    def _post(self, payload, client=None, **extra):
        return (client or self.client).post(
            reverse("user-legal-acceptances"),
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    def test_should_record_the_acceptance_and_write_an_audit_entry(self):
        self.client.force_login(self.user)

        response = self._post(self._payload(), REMOTE_ADDR="203.0.113.9")

        body = response.json()
        audit = AuditLog.objects.get(entity="user_legal_acceptance", entity_id=body["id"])
        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["version"]["id"], self.version.pk)
        self.assertEqual(
            [(consent["code"], consent["accepted"]) for consent in body["consents"]],
            [("objeto", True), ("comunicados", False)],
        )
        self.assertEqual(audit.action, AuditAction.CREATE)
        self.assertEqual(audit.entity, "user_legal_acceptance")
        self.assertEqual(audit.entity_id, body["id"])
        self.assertEqual(audit.user, self.user)
        self.assertEqual(audit.ip_address, "203.0.113.9")
        self.assertIsNotNone(audit.occurred_at)
        self.assertEqual(
            audit.record,
            {
                "event": "LEGAL_TERMS_ACCEPTED",
                "document": self.document.slug,
                "version": self.version.version,
                "declined_clauses": ["comunicados"],
                "actor": {
                    "id": self.user.pk,
                    "name": self.user.name,
                    "authenticated": True,
                },
            },
        )

    def test_should_roll_back_acceptance_when_the_audit_write_fails(self):
        self.client.force_login(self.user)

        with (
            mock.patch.object(AuditLog.objects, "create", side_effect=DatabaseError("db down")),
            self.assertLogs("core.services.audit_service", level="ERROR"),
        ):
            response = self._post(self._payload())

        self.assertEqual(response.status_code, 503)
        self.assertFalse(UserLegalAcceptance.objects.exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_should_record_the_acceptance_for_the_authenticated_user_only(self):
        self.client.force_login(self.user)
        payload = {**self._payload(), "user_id": self.other_user.pk}

        self._post(payload)

        self.assertEqual(
            list(UserLegalAcceptance.objects.values_list("user_id", flat=True)), [self.user.pk]
        )

    def test_should_require_authentication_to_accept(self):
        response = self._post(self._payload())

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})
        self.assertFalse(UserLegalAcceptance.objects.exists())

    def test_should_reject_declining_a_required_clause(self):
        self.client.force_login(self.user)
        payload = self._payload()
        payload["consents"][0]["accepted"] = False

        response = self._post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["consents"]["code"], "required_clause_declined")

    def test_should_reject_a_malformed_json_body(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("user-legal-acceptances"), data="{version", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "InvalidJSON"})

    def test_should_answer_not_found_for_an_unpublished_version(self):
        draft = self._version(2, LegalDocumentStatus.DRAFT)
        self.client.force_login(self.user)

        response = self._post({"version_id": draft.pk, "consents": []})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "LegalVersionNotFound"})

    def test_should_answer_conflict_for_an_outdated_version(self):
        newer = self._version(2, LegalDocumentStatus.PUBLISHED)
        self.client.force_login(self.user)

        response = self._post(self._payload())

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"error": "OutdatedLegalVersion", "current_version_id": newer.pk}
        )

    def test_should_answer_conflict_for_a_version_already_accepted(self):
        self.client.force_login(self.user)
        self._post(self._payload())

        response = self._post(self._payload(optional_accepted=True))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "LegalVersionAlreadyAccepted"})

    def test_should_reject_an_acceptance_without_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = self._post(self._payload(), client=client)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserLegalAcceptance.objects.exists())

    def test_should_return_the_history_of_the_authenticated_user(self):
        record_acceptance(self.user, self._payload())
        record_acceptance(self.other_user, self._payload())
        self.client.force_login(self.user)

        response = self.client.get(reverse("user-legal-acceptances"))

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["document"]["slug"], self.document.slug)
        self.assertEqual(len(body["results"][0]["consents"]), 2)
        self.assertNotIn("ip_address", body["results"][0])

    def test_should_require_authentication_to_read_the_history(self):
        response = self.client.get(reverse("user-legal-acceptances"))

        self.assertEqual(response.status_code, 401)

    def test_should_reject_methods_other_than_get_and_post(self):
        self.client.force_login(self.user)

        response = self.client.delete(reverse("user-legal-acceptances"))

        self.assertEqual(response.status_code, 405)
