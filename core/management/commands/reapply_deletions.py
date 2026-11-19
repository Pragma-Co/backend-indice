from django.core.management.base import BaseCommand, CommandError

from core.models import User
from core.services.excluded_identifier_service import excluded_identifier_hashes, hash_identifier
from core.services.user_anonymization_service import (
    NoReplacementManagerError,
    anonymize_user,
    delete_user_account,
)


class Command(BaseCommand):
    help = "Delete again the accounts brought back by a backup restore (LGPD tombstone check)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--hard", action="store_true")

    def handle(self, *args, dry_run, hard, **options):
        hashes = excluded_identifier_hashes()
        restored = [user for user in User.objects.order_by("pk") if hash_identifier(user.email) in hashes]

        if dry_run:
            for user in restored:
                self.stdout.write(f"Would delete user {user.pk}.")
            self.stdout.write(f"{len(restored)} restored user(s) found; nothing changed.")
            return

        action = delete_user_account if hard else anonymize_user
        deleted = 0
        failed = []
        for user in restored:
            try:
                action(user)
            except NoReplacementManagerError:
                failed.append(user.pk)
                continue
            deleted += 1
            self.stdout.write(f"Deleted user {user.pk}.")

        self.stdout.write(f"{deleted} restored user(s) deleted again.")
        if failed:
            raise CommandError(f"No replacement manager available for user(s): {failed}.")
