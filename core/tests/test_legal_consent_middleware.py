from datetime import timedelta

from django.test import TestCase
from django.urls import reverse

from core.models import LegalDocumentStatus, UserLegalAcceptance
from core.tests.test_legal_consent import LegalConsentFixtureMixin


class LegalConsentRequiredMiddlewareTests(LegalConsentFixtureMixin, TestCase):
    def _accept(self):
        UserLegalAcceptance.objects.create(user=self.user, version=self.version, accepted=True)

    def test_should_block_protected_routes_while_terms_are_pending(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("document-list"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "LegalAcceptanceRequired"})

    def test_should_keep_consent_and_session_routes_available(self):
        self.client.force_login(self.user)

        for name in ("user-me", "user-legal-pending", "user-legal-acceptances"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_should_list_pending_documents_and_unblock_after_acceptance(self):
        self.client.force_login(self.user)

        pending = self.client.get(reverse("user-legal-pending")).json()
        self.assertEqual([item["slug"] for item in pending["results"]], [self.document.slug])

        self._accept()

        self.assertEqual(self.client.get(reverse("user-legal-pending")).json()["count"], 0)
        self.assertNotEqual(self.client.get(reverse("document-list")).status_code, 403)

    def test_should_block_again_when_a_new_version_is_published(self):
        self._accept()
        self.client.force_login(self.user)
        self.assertNotEqual(self.client.get(reverse("document-list")).status_code, 403)

        self._version(2, LegalDocumentStatus.PUBLISHED)

        self.assertEqual(self.client.get(reverse("document-list")).status_code, 403)

    def test_should_block_again_after_revoking_the_acceptance(self):
        acceptance = UserLegalAcceptance.objects.create(
            user=self.user, version=self.version, accepted=True
        )
        UserLegalAcceptance.objects.filter(pk=acceptance.pk).update(
            revoked_at=acceptance.accepted_at + timedelta(minutes=1)
        )
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(reverse("document-list")).status_code, 403)
