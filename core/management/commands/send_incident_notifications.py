from django.core.management.base import BaseCommand, CommandError

from core.services.incident_subject_notification_service import retry_subject_notifications


class Command(BaseCommand):
    help = (
        "Retry the pending or failed e-mail communications of open data incidents "
        "to the affected users."
    )

    def add_arguments(self, parser):
        parser.add_argument("--incident", type=int, default=None)

    def handle(self, *args, incident, **options):
        results = retry_subject_notifications(incident_id=incident)
        if not results:
            self.stdout.write("No pending communications.")
            return
        failed = []
        for result in results:
            outcome = result["outcome"]
            reference = result["incident"].reference
            self.stdout.write(
                f"{reference}: sent {outcome['sent']}, failed {outcome['failed']}, "
                f"skipped {outcome['skipped']}"
            )
            if outcome["failed"]:
                failed.append(reference)
        if failed:
            raise CommandError(
                f"Communications still failing for {', '.join(failed)}; "
                "see data_incident_subject_notification."
            )
