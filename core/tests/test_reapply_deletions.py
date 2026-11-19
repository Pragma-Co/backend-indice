from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from core.models import Area, ExcludedIdentifier, Role, User
from core.services.user_anonymization_service import (
    anonymize_user,
    anonymized_email,
    delete_user_account,
)


@override_settings(EXCLUDED_IDENTIFIER_HMAC_KEY="test-only-stable-key")
class ReapplyDeletionsTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Sup3r-secret-pass",
            name="Admin",
            role=Role.ADMIN,
            area=self.area,
        )
        self.kept = User.objects.create_user(
            email="kept@example.com",
            password="Sup3r-secret-pass",
            name="Kept",
            role=Role.AUTHOR,
            area=self.area,
        )
        self.removed = User.objects.create_user(
            email="removed@example.com",
            password="Sup3r-secret-pass",
            name="Removed",
            role=Role.AUTHOR,
            area=self.area,
        )

    def restore_removed_user(self):
        anonymize_user(self.removed)
        User.objects.filter(pk=self.removed.pk).update(
            email="removed@example.com", name="Removed", is_active=True
        )

    def run_command(self, *args):
        output = StringIO()
        call_command("reapply_deletions", *args, stdout=output)
        return output.getvalue()

    def test_should_store_excluded_identifiers_in_the_tombstone_database(self):
        anonymize_user(self.removed)

        self.assertEqual(ExcludedIdentifier.objects.db, "tombstone")
        self.assertEqual(ExcludedIdentifier.objects.using("tombstone").count(), 1)

    def test_should_anonymize_restored_user_whose_identifier_was_excluded(self):
        self.restore_removed_user()

        self.run_command()

        self.removed.refresh_from_db()
        self.assertEqual(self.removed.email, anonymized_email(self.removed.pk))
        self.assertFalse(self.removed.is_active)

    def test_should_keep_users_without_an_excluded_identifier(self):
        self.restore_removed_user()

        self.run_command()

        self.kept.refresh_from_db()
        self.assertEqual(self.kept.email, "kept@example.com")
        self.assertTrue(self.kept.is_active)

    def test_should_not_change_anything_on_dry_run(self):
        self.restore_removed_user()

        output = self.run_command("--dry-run")

        self.removed.refresh_from_db()
        self.assertEqual(self.removed.email, "removed@example.com")
        self.assertIn(f"Would delete user {self.removed.pk}.", output)

    def test_should_not_print_email_addresses(self):
        self.restore_removed_user()

        output = self.run_command()

        self.assertNotIn("removed@example.com", output)

    def test_should_be_idempotent(self):
        self.restore_removed_user()
        self.run_command()

        output = self.run_command()

        self.assertIn("0 restored user(s) deleted again.", output)

    def test_should_hard_delete_restored_user_with_hard_flag(self):
        self.restore_removed_user()

        self.run_command("--hard")

        self.assertFalse(User.objects.filter(pk=self.removed.pk).exists())

    def test_should_delete_again_a_hard_deleted_user_brought_back_by_restore(self):
        delete_user_account(self.removed)
        restored = User(
            email="removed@example.com",
            name="Removed",
            role=Role.AUTHOR,
            area=self.area,
            is_active=True,
        )
        restored.set_unusable_password()
        restored.save()

        self.run_command()

        restored.refresh_from_db()
        self.assertEqual(restored.email, anonymized_email(restored.pk))

    def test_should_fail_when_no_replacement_manager_is_available(self):
        self.restore_removed_user()
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        User.objects.filter(pk=self.kept.pk).update(is_active=False)

        with self.assertRaises(CommandError):
            self.run_command()
