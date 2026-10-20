"""Hard delete of a user account: removes the row and hands over its work."""

from django.core.management.base import BaseCommand, CommandError

from core.models import User
from core.services.user_anonymization_service import NoReplacementManagerError, delete_user_account


class Command(BaseCommand):
    help = "Permanently delete a user (hard delete), reassigning their work to another manager."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError("User not found.")
        try:
            summary = delete_user_account(user)
        except NoReplacementManagerError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"User {user.pk} deleted; work reassigned to {summary['reassigned_to']}.")
