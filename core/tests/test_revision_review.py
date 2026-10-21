import json

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    Role,
    User,
)
from core.services.revision_review_exceptions import (
    OutdatedRevisionError,
    OwnRevisionReviewError,
    RevisionAlreadyDecidedError,
    RevisionNotFoundError,
    RevisionReviewValidationError,
)
from core.services.revision_review_service import decide_revision, validate_decision_payload

JUSTIFICATION = "Furação diverge do ensaio de tração aprovado"


class RevisionReviewFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.author = User.objects.create_user(
            email="author@example.com",
            password="secret",
            name="Author",
            area=self.area,
            role=Role.AUTHOR,
        )
        self.manager = User.objects.create_user(
            email="manager@example.com",
            password="secret",
            name="Manager",
            area=self.area,
            role=Role.AUDITOR,
        )
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.document = Document.objects.create(
            code="AK-2100-EST-DWG-0001",
            title="Desenho da caverna 14",
            project=Project.objects.create(code="AK-2100", name="Fuselagem"),
            discipline=Discipline.objects.create(code="EST", name="Estruturas"),
            document_type=self.document_type,
            confidentiality_level="PUBLIC",
            responsible=self.author,
            created_by=self.author,
        )
        self.current = self._revision(1, RevisionStatus.APPROVED)
        self.pending = self._revision(2, RevisionStatus.PENDING)

    def _revision(self, version, status, document=None):
        decided = status != RevisionStatus.PENDING
        revision = Revision.objects.create(
            document=document or self.document,
            version=version,
            status=status,
            change_description="Atualiza a furação da caverna 14",
            author=self.author,
            auditor=self.manager if decided else None,
            audited_at=timezone.now() if decided else None,
        )
        File.objects.create(
            revision=revision,
            original_name=f"caverna-v{version}.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256=f"{version:064x}",
            storage_path=f"{revision.document.code}/v{version}.pdf",
        )
        return revision


class DecideRevisionServiceTests(RevisionReviewFixtureMixin, TestCase):
    def test_should_make_the_approved_revision_current_and_obsolete_the_previous_one(self):
        revision, superseded = decide_revision(
            self.pending.pk, self.manager, {"decision": "APPROVED"}
        )

        self.current.refresh_from_db()
        self.document.refresh_from_db()
        self.assertEqual(revision.status, RevisionStatus.APPROVED)
        self.assertEqual(revision.auditor, self.manager)
        self.assertIsNotNone(revision.audited_at)
        self.assertEqual(superseded.pk, self.current.pk)
        self.assertEqual(self.current.status, RevisionStatus.OBSOLETE)
        self.assertEqual(self.document.updated_by, self.manager)
        self.assertEqual(
            Revision.objects.get(document=self.document, status=RevisionStatus.APPROVED).pk,
            self.pending.pk,
        )

    def test_should_approve_the_first_revision_when_the_document_has_no_current_one(self):
        self.current.delete()

        revision, superseded = decide_revision(
            self.pending.pk, self.manager, {"decision": "approved", "justification": ""}
        )

        self.assertEqual(revision.status, RevisionStatus.APPROVED)
        self.assertIsNone(superseded)

    def test_should_reject_with_justification_and_keep_the_previous_revision_current(self):
        revision, superseded = decide_revision(
            self.pending.pk,
            self.manager,
            {"decision": "REJECTED", "justification": f"  {JUSTIFICATION}  "},
        )

        self.current.refresh_from_db()
        self.assertEqual(revision.status, RevisionStatus.REJECTED)
        self.assertEqual(revision.auditor_comment, JUSTIFICATION)
        self.assertIsNone(superseded)
        self.assertEqual(self.current.status, RevisionStatus.APPROVED)

    def test_should_refuse_rejection_without_justification(self):
        with self.assertRaises(RevisionReviewValidationError) as context:
            decide_revision(self.pending.pk, self.manager, {"decision": "REJECTED"})

        self.pending.refresh_from_db()
        self.assertEqual(context.exception.errors["justification"]["code"], "required")
        self.assertEqual(self.pending.status, RevisionStatus.PENDING)

    def test_should_refuse_a_revision_that_was_already_decided(self):
        decide_revision(self.pending.pk, self.manager, {"decision": "APPROVED"})

        with self.assertRaises(RevisionAlreadyDecidedError) as context:
            decide_revision(
                self.pending.pk,
                self.manager,
                {"decision": "REJECTED", "justification": JUSTIFICATION},
            )

        self.assertEqual(context.exception.status, RevisionStatus.APPROVED)

    def test_should_refuse_a_reviewer_deciding_on_their_own_revision(self):
        self.author.role = Role.AUDITOR
        self.author.save(update_fields=["role"])

        with self.assertRaises(OwnRevisionReviewError):
            decide_revision(self.pending.pk, self.author, {"decision": "APPROVED"})

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, RevisionStatus.PENDING)

    def test_should_refuse_approving_a_revision_older_than_the_current_one(self):
        newer = self._revision(3, RevisionStatus.PENDING)
        decide_revision(newer.pk, self.manager, {"decision": "APPROVED"})

        with self.assertRaises(OutdatedRevisionError) as context:
            decide_revision(self.pending.pk, self.manager, {"decision": "APPROVED"})

        self.pending.refresh_from_db()
        self.assertEqual(context.exception.current_version, 3)
        self.assertEqual(self.pending.status, RevisionStatus.PENDING)

    def test_should_raise_not_found_for_missing_or_inactive_type_revisions(self):
        self.document_type.active = False
        self.document_type.save(update_fields=["active"])

        with self.assertRaises(RevisionNotFoundError):
            decide_revision(self.pending.pk, self.manager, {"decision": "APPROVED"})
        with self.assertRaises(RevisionNotFoundError):
            decide_revision(999999, self.manager, {"decision": "APPROVED"})


class ValidateDecisionPayloadTests(RevisionReviewFixtureMixin, TestCase):
    def test_should_report_invalid_payloads_by_field(self):
        cases = [
            ([], "body", "invalid"),
            ({}, "decision", "required"),
            ({"decision": "  "}, "decision", "required"),
            ({"decision": "OBSOLETE"}, "decision", "invalid_choice"),
            ({"decision": 1}, "decision", "invalid_choice"),
            ({"decision": "REJECTED", "justification": 42}, "justification", "invalid"),
            ({"decision": "REJECTED", "justification": "curta"}, "justification", "too_short"),
            ({"decision": "APPROVED", "justification": "x" * 1001}, "justification", "too_long"),
        ]

        results = []
        for payload, _field, _code in cases:
            try:
                validate_decision_payload(payload)
                results.append(None)
            except RevisionReviewValidationError as exc:
                results.append(exc.errors)

        for (payload, field, code), errors in zip(cases, results, strict=True):
            with self.subTest(payload=payload):
                self.assertEqual(errors[field]["code"], code)


class PendingRevisionsViewTests(RevisionReviewFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("manager-pending-revisions")

    def test_should_list_only_pending_revisions_oldest_first(self):
        other_document = Document.objects.create(
            code="AK-2100-EST-DWG-0002",
            title="Desenho da caverna 15",
            project=self.document.project,
            discipline=self.document.discipline,
            document_type=self.document_type,
            responsible=self.author,
            created_by=self.author,
        )
        newer = self._revision(1, RevisionStatus.PENDING, document=other_document)
        self.client.force_login(self.manager)

        response = self.client.get(self.url)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual([item["id"] for item in body["results"]], [self.pending.pk, newer.pk])
        first = body["results"][0]
        self.assertEqual(first["revision"], "REV02")
        self.assertEqual(first["document"]["code"], self.document.code)
        self.assertEqual(first["author"]["name"], "Author")
        self.assertEqual(first["files"][0]["original_name"], "caverna-v2.pdf")

    def test_should_paginate_and_validate_query_parameters(self):
        self.client.force_login(self.manager)

        paged = self.client.get(self.url, {"page": "2", "page_size": "1"})
        invalid = self.client.get(self.url, {"page": "0", "page_size": "500"})

        self.assertEqual(paged.status_code, 200)
        self.assertEqual(paged.json()["results"], [])
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(set(invalid.json()["errors"]), {"page", "page_size"})

    def test_should_require_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})

    def test_should_forbid_users_without_manager_role(self):
        self.client.force_login(self.author)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "PermissionDenied"})

    def test_should_allow_administrators(self):
        admin = User.objects.create_user(
            email="admin@example.com",
            password="secret",
            name="Admin",
            area=self.area,
            role=Role.ADMIN,
        )
        self.client.force_login(admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_should_reject_other_http_methods(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)

        response = client.post(self.url)

        self.assertEqual(response.status_code, 405)


class RevisionDecisionViewTests(RevisionReviewFixtureMixin, TestCase):
    def _post(self, revision_id, payload, raw=None):
        return self.client.post(
            reverse("manager-revision-decision", args=[revision_id]),
            data=raw if raw is not None else json.dumps(payload),
            content_type="application/json",
        )

    def test_should_approve_and_record_the_decision_in_the_audit_trail(self):
        self.client.force_login(self.manager)

        response = self._post(self.pending.pk, {"decision": "APPROVED"})

        body = response.json()
        audit = AuditLog.objects.get(entity="revision")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], RevisionStatus.APPROVED)
        self.assertEqual(body["auditor"]["id"], self.manager.pk)
        self.assertEqual(body["superseded_revision"]["id"], self.current.pk)
        self.assertEqual(body["superseded_revision"]["status"], RevisionStatus.OBSOLETE)
        self.assertEqual(audit.action, AuditAction.UPDATE)
        self.assertEqual(audit.entity_id, self.pending.pk)
        self.assertEqual(audit.user, self.manager)
        self.assertEqual(audit.record["event"], "REVISION_APPROVED")

    def test_should_reject_with_justification(self):
        self.client.force_login(self.manager)

        response = self._post(
            self.pending.pk, {"decision": "REJECTED", "justification": JUSTIFICATION}
        )

        self.current.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], RevisionStatus.REJECTED)
        self.assertEqual(response.json()["auditor_comment"], JUSTIFICATION)
        self.assertIsNone(response.json()["superseded_revision"])
        self.assertEqual(self.current.status, RevisionStatus.APPROVED)

    def test_should_answer_400_for_rejection_without_justification(self):
        self.client.force_login(self.manager)

        response = self._post(self.pending.pk, {"decision": "REJECTED", "justification": " "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["justification"]["code"], "required")

    def test_should_answer_400_for_malformed_json(self):
        self.client.force_login(self.manager)

        response = self._post(self.pending.pk, None, raw="{invalid")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "InvalidJSON"})

    def test_should_answer_401_without_authentication(self):
        response = self._post(self.pending.pk, {"decision": "APPROVED"})

        self.pending.refresh_from_db()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.pending.status, RevisionStatus.PENDING)

    def test_should_answer_403_for_users_without_manager_role(self):
        self.client.force_login(self.author)

        response = self._post(self.pending.pk, {"decision": "APPROVED"})

        self.pending.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "PermissionDenied"})
        self.assertEqual(self.pending.status, RevisionStatus.PENDING)

    def test_should_answer_403_when_the_manager_authored_the_revision(self):
        self.author.role = Role.AUDITOR
        self.author.save(update_fields=["role"])
        self.client.force_login(self.author)

        response = self._post(self.pending.pk, {"decision": "APPROVED"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "CannotReviewOwnRevision"})

    def test_should_answer_404_for_unknown_revision(self):
        self.client.force_login(self.manager)

        response = self._post(999999, {"decision": "APPROVED"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "RevisionNotFound"})

    def test_should_answer_409_for_a_revision_already_decided(self):
        self.client.force_login(self.manager)

        response = self._post(self.current.pk, {"decision": "APPROVED"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "RevisionAlreadyDecided", "status": "APPROVED"})

    def test_should_answer_409_when_a_newer_version_is_already_current(self):
        newer = self._revision(3, RevisionStatus.PENDING)
        self.client.force_login(self.manager)
        self._post(newer.pk, {"decision": "APPROVED"})

        response = self._post(self.pending.pk, {"decision": "APPROVED"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "OutdatedRevision", "current_version": 3})

    def test_should_reject_get_requests(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)

        response = client.get(reverse("manager-revision-decision", args=[self.pending.pk]))

        self.assertEqual(response.status_code, 405)
