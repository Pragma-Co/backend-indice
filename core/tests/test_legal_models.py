from django.test import TestCase

from core.models import (
    Area,
    LegalClause,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentVersion,
    User,
    UserClauseConsent,
    UserLegalAcceptance,
)


class LegalDocumentModelTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engineering")
        self.user = User.objects.create_user(
            email="legal@example.com",
            password="test-password",
            name="Legal User",
            area=self.area,
        )
        self.document = LegalDocument.objects.create(
            slug="terms-of-use",
            title="Terms of Use",
        )

    def test_should_persist_incremental_versions_and_required_optional_clauses(self):
        first_version = self.document.create_next_version(created_by=self.user)
        first_version.status = LegalDocumentStatus.PUBLISHED
        first_version.published_at = "2026-10-01T00:00:00Z"
        first_version.save(update_fields=["status", "published_at"])
        second_version = self.document.create_next_version(
            created_by=self.user,
            change_notes="Adds an optional newsletter clause.",
        )
        required_clause = LegalClause.objects.create(
            version=second_version,
            code="data-processing",
            position=1,
            title="Data processing",
            body="I agree to the required processing.",
            is_required=True,
        )
        optional_clause = LegalClause.objects.create(
            version=second_version,
            code="newsletter",
            position=2,
            title="Newsletter",
            body="I agree to receive optional updates.",
            is_required=False,
        )

        self.assertEqual(
            list(self.document.versions.order_by("version").values_list("version", flat=True)),
            [1, 2],
        )
        self.assertEqual(first_version.version, 1)
        self.assertTrue(required_clause.is_required)
        self.assertFalse(optional_clause.is_required)

    def test_should_return_highest_published_version_as_current(self):
        first_published = LegalDocumentVersion.objects.create(
            document=self.document,
            version=1,
            status=LegalDocumentStatus.PUBLISHED,
            created_by=self.user,
            published_at="2026-10-01T00:00:00Z",
        )
        LegalDocumentVersion.objects.create(
            document=self.document,
            version=2,
            created_by=self.user,
        )
        second_published = LegalDocumentVersion.objects.create(
            document=self.document,
            version=3,
            status=LegalDocumentStatus.PUBLISHED,
            created_by=self.user,
            published_at="2026-10-10T00:00:00Z",
        )

        self.assertEqual(self.document.current_published_version, second_published)

        second_published.status = LegalDocumentStatus.RETIRED
        second_published.save(update_fields=["status"])

        self.assertEqual(self.document.current_published_version, first_published)

    def test_should_persist_acceptance_and_clause_decisions(self):
        version = LegalDocumentVersion.objects.create(
            document=self.document,
            version=1,
            status=LegalDocumentStatus.PUBLISHED,
            created_by=self.user,
            published_at="2026-10-01T00:00:00Z",
        )
        clause = LegalClause.objects.create(
            version=version,
            code="optional-notice",
            position=1,
            title="Optional notice",
            body="I agree to receive notices.",
            is_required=False,
        )
        acceptance = UserLegalAcceptance.objects.create(user=self.user, version=version)

        UserClauseConsent.objects.create(
            acceptance=acceptance,
            clause=clause,
            accepted=False,
        )

        saved_consent = UserClauseConsent.objects.get(acceptance=acceptance, clause=clause)
        self.assertFalse(saved_consent.accepted)
