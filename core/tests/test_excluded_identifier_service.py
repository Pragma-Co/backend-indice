from django.test import TestCase, override_settings

from core.models import Area, ExcludedIdentifier, User
from core.services.excluded_identifier_service import (
    ExcludedIdentifierError,
    is_identifier_excluded,
    store_excluded_identifier,
)


@override_settings(EXCLUDED_IDENTIFIER_HMAC_KEY="test-only-stable-key")
class ExcludedIdentifierServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="SEC", name="Segurança")

    def test_store_persists_only_a_hash_and_timestamp(self):
        excluded = store_excluded_identifier("Sensitive.User@example.com")

        self.assertEqual(len(excluded.identifier_hash), 64)
        self.assertNotIn("Sensitive.User@example.com", excluded.identifier_hash)
        self.assertIsNotNone(excluded.created_at)
        self.assertTrue(is_identifier_excluded(" sensitive.user@EXAMPLE.com "))
        self.assertEqual(ExcludedIdentifier.objects.count(), 1)

    def test_excluded_identifier_cannot_be_used_to_create_an_account(self):
        store_excluded_identifier("blocked@example.com")

        with self.assertRaises(ExcludedIdentifierError):
            User.objects.create_user(
                email="BLOCKED@example.com",
                password="secret",
                name="Blocked",
                area=self.area,
            )

        self.assertFalse(User.objects.filter(email__iexact="blocked@example.com").exists())
