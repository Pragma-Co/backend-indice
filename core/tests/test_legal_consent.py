import json
from unittest import mock

from django.db import DatabaseError, IntegrityError, transaction
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
    LegalAcceptanceAlreadyRevokedError,
    LegalAcceptanceNotFoundError,
    LegalConsentValidationError,
    LegalDocumentNotFoundError,
    LegalVersionAlreadyAcceptedError,
    LegalVersionNotFoundError,
    OutdatedLegalVersionError,
)
from core.services.legal_consent_service import (
    current_legal_version,
    record_acceptance,
    revoke_acceptance,
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


class RevokeAcceptanceTests(LegalConsentFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.acceptance = record_acceptance(self.user, self._payload())

    def _revoke(self, acceptance_id=None, client=None):
        return (client or self.client).post(
            reverse(
                "user-legal-acceptance-revoke",
                kwargs={"acceptance_id": acceptance_id or self.acceptance.pk},
            )
        )

    def test_should_mark_the_acceptance_as_revoked_and_keep_it_in_the_history(self):
        revoked = revoke_acceptance(self.user, self.acceptance.pk)

        self.user.refresh_from_db()
        self.assertIsNotNone(revoked.revoked_at)
        self.assertEqual(UserLegalAcceptance.objects.filter(user=self.user).count(), 1)
        self.assertEqual(UserClauseConsent.objects.filter(acceptance=revoked).count(), 2)
        self.assertIsNone(self.user.terms_accepted_at)

    def test_should_keep_the_date_of_another_acceptance_still_in_force(self):
        other_document = LegalDocument.objects.create(slug="politica", title="Política")
        other_version = LegalDocumentVersion.objects.create(
            document=other_document,
            version=1,
            status=LegalDocumentStatus.PUBLISHED,
            content_hash="b" * 64,
            created_by=self.user,
            published_at=timezone.now(),
        )
        clause = LegalClause.objects.create(
            version=other_version, code="aceite", position=1, title="Artigo 1", body="Texto."
        )
        other = record_acceptance(
            self.user,
            {
                "version_id": other_version.pk,
                "consents": [{"clause_id": clause.pk, "accepted": True}],
            },
        )

        revoke_acceptance(self.user, self.acceptance.pk)

        self.user.refresh_from_db()
        self.assertEqual(self.user.terms_accepted_at, other.accepted_at)

    def test_should_not_revoke_twice(self):
        revoke_acceptance(self.user, self.acceptance.pk)

        with self.assertRaises(LegalAcceptanceAlreadyRevokedError):
            revoke_acceptance(self.user, self.acceptance.pk)

    def test_should_not_revoke_the_acceptance_of_another_user(self):
        with self.assertRaises(LegalAcceptanceNotFoundError):
            revoke_acceptance(self.other_user, self.acceptance.pk)

        self.acceptance.refresh_from_db()
        self.assertIsNone(self.acceptance.revoked_at)

    def test_should_let_the_user_accept_the_same_version_again_after_revoking(self):
        revoked = revoke_acceptance(self.user, self.acceptance.pk)

        renewed = record_acceptance(self.user, self._payload(optional_accepted=True))

        self.user.refresh_from_db()
        revoked.refresh_from_db()
        self.assertNotEqual(renewed.pk, revoked.pk)
        self.assertIsNone(renewed.revoked_at)
        self.assertIsNotNone(revoked.revoked_at)
        self.assertEqual(UserLegalAcceptance.objects.filter(user=self.user).count(), 2)
        self.assertEqual(self.user.terms_accepted_at, renewed.accepted_at)
        self.assertEqual(list(user_acceptances(self.user)), [renewed, revoked])

    def test_should_still_refuse_a_new_acceptance_while_one_is_in_force(self):
        revoke_acceptance(self.user, self.acceptance.pk)
        record_acceptance(self.user, self._payload())

        with self.assertRaises(LegalVersionAlreadyAcceptedError):
            record_acceptance(self.user, self._payload())

        self.assertEqual(UserLegalAcceptance.objects.filter(user=self.user).count(), 2)

    def test_database_should_allow_only_one_acceptance_in_force_per_version(self):
        revoke_acceptance(self.user, self.acceptance.pk)
        UserLegalAcceptance.objects.create(user=self.user, version=self.version)

        with self.assertRaises(IntegrityError), transaction.atomic():
            UserLegalAcceptance.objects.create(user=self.user, version=self.version)

        self.assertEqual(UserLegalAcceptance.objects.filter(user=self.user).count(), 2)

    def test_endpoint_should_revoke_and_write_an_audit_entry(self):
        self.client.force_login(self.user)

        response = self._revoke()

        body = response.json()
        audit = AuditLog.objects.get(action=AuditAction.UPDATE, entity="user_legal_acceptance")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["id"], self.acceptance.pk)
        self.assertIsNotNone(body["revoked_at"])
        self.assertEqual(audit.entity_id, self.acceptance.pk)
        self.assertEqual(audit.user, self.user)
        self.assertEqual(audit.record["event"], "LEGAL_TERMS_REVOKED")
        self.assertEqual(audit.record["document"], "termo-tratamento-dados")

    def test_endpoint_should_roll_back_the_revocation_when_the_audit_write_fails(self):
        self.client.force_login(self.user)

        with (
            mock.patch.object(AuditLog.objects, "create", side_effect=DatabaseError("db down")),
            self.assertLogs("core.services.audit_service", level="ERROR"),
        ):
            response = self._revoke()

        self.acceptance.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "AuditUnavailable"})
        self.assertIsNone(self.acceptance.revoked_at)
        self.assertEqual(self.user.terms_accepted_at, self.acceptance.accepted_at)
        self.assertFalse(AuditLog.objects.exists())

    def test_endpoint_should_answer_409_for_an_acceptance_already_revoked(self):
        self.client.force_login(self.user)
        self._revoke()

        response = self._revoke()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "LegalAcceptanceAlreadyRevoked"})

    def test_endpoint_should_answer_404_for_another_user_or_an_unknown_acceptance(self):
        self.client.force_login(self.other_user)

        foreign = self._revoke()
        unknown = self._revoke(acceptance_id=999999)

        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(foreign.json(), {"error": "LegalAcceptanceNotFound"})
        self.assertEqual(unknown.status_code, 404)

    def test_endpoint_should_accept_the_version_again_after_revoking(self):
        self.client.force_login(self.user)
        self._revoke()

        response = self.client.post(
            reverse("user-legal-acceptances"),
            data=json.dumps(self._payload()),
            content_type="application/json",
        )
        history = self.client.get(reverse("user-legal-acceptances")).json()

        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()["id"], self.acceptance.pk)
        self.assertEqual(history["count"], 2)
        self.assertEqual([item["revoked_at"] is None for item in history["results"]], [True, False])

    def test_endpoint_should_require_a_session(self):
        response = self._revoke(client=Client())

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})

    def test_endpoint_should_only_accept_post(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("user-legal-acceptance-revoke", kwargs={"acceptance_id": self.acceptance.pk})
        )

        self.assertEqual(response.status_code, 405)


class LegalVersionViewTests(LegalConsentFixtureMixin, TestCase):
    def _get(self, version_id):
        return self.client.get(reverse("legal-version-detail", kwargs={"version_id": version_id}))

    def test_should_return_a_published_version_with_its_clauses_in_order(self):
        response = self._get(self.version.pk)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["id"], self.version.pk)
        self.assertEqual(
            body["document"], {"slug": self.document.slug, "title": self.document.title}
        )
        self.assertEqual([clause["code"] for clause in body["clauses"]], ["objeto", "comunicados"])
        self.assertEqual(body["clauses"][0]["body"], "Texto da cláusula objeto.")
        self.assertEqual(body["summary"], "Declaração do Titular.")

    def test_should_return_a_retired_version_that_someone_may_have_accepted(self):
        retired = self._version(2, LegalDocumentStatus.RETIRED)

        response = self._get(retired.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 2)

    def test_should_answer_not_found_for_draft_and_unknown_versions(self):
        draft = self._version(3, LegalDocumentStatus.DRAFT)

        responses = (self._get(draft.pk), self._get(999999))

        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"error": "LegalVersionNotFound"})

    def test_should_reject_methods_other_than_get(self):
        response = self.client.post(
            reverse("legal-version-detail", kwargs={"version_id": self.version.pk})
        )

        self.assertEqual(response.status_code, 405)


class LegalDocumentsViewTests(LegalConsentFixtureMixin, TestCase):
    def test_should_list_documents_with_their_current_published_version_ordered_by_title(self):
        newer = self._version(2, LegalDocumentStatus.PUBLISHED)
        self._clause(newer, "objeto", 1, is_required=True)
        self._version(3, LegalDocumentStatus.DRAFT)
        policy = LegalDocument.objects.create(
            slug="politica-privacidade", title="Política de Privacidade"
        )
        policy_version = LegalDocumentVersion.objects.create(
            document=policy,
            version=1,
            status=LegalDocumentStatus.PUBLISHED,
            content_hash="c" * 64,
            created_by=self.user,
            published_at=timezone.now(),
        )
        self._clause(policy_version, "aceite", 1, is_required=False)
        LegalDocument.objects.create(slug="sem-versao", title="Documento sem versão")

        response = self.client.get(reverse("legal-document-list"))

        body = response.json()
        term = body["results"][1]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual(
            [item["slug"] for item in body["results"]],
            ["politica-privacidade", "termo-tratamento-dados"],
        )
        self.assertEqual(term["title"], self.document.title)
        self.assertEqual(term["current_version"]["id"], newer.pk)
        self.assertEqual(term["current_version"]["version"], 2)
        self.assertEqual(
            term["current_version"]["clauses"],
            [
                {
                    "id": newer.clauses.get().pk,
                    "code": "objeto",
                    "position": 1,
                    "title": "Artigo 1",
                    "is_required": True,
                }
            ],
        )
        self.assertFalse(body["results"][0]["current_version"]["clauses"][0]["is_required"])

    def test_should_leave_out_documents_without_a_published_version(self):
        self.version.status = LegalDocumentStatus.RETIRED
        self.version.save(update_fields=["status"])
        self._version(2, LegalDocumentStatus.DRAFT)

        response = self.client.get(reverse("legal-document-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"count": 0, "results": []})

    def test_should_reject_methods_other_than_get(self):
        response = self.client.post(reverse("legal-document-list"))

        self.assertEqual(response.status_code, 405)
