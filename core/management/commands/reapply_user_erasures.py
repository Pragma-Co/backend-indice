from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.backup_service import BackupConfigurationError, BackupFileError
from core.services.user_erasure_reapplication_service import (
    load_register_from_snapshot,
    reapply_user_erasures,
)


class Command(BaseCommand):
    help = (
        "Re-apply the anonymizations and deletions of the exclusion register "
        "to the users of a restored database."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from-snapshot", default=None)

    def handle(self, *args, from_snapshot, **options):
        if from_snapshot:
            source = Path(from_snapshot)
            if not source.is_file():
                raise CommandError(f"{from_snapshot} does not exist.")
            try:
                merged = load_register_from_snapshot(source)
            except (BackupConfigurationError, BackupFileError, ValueError, KeyError) as exc:
                raise CommandError(str(exc) or type(exc).__name__) from exc
            except Exception as exc:
                raise CommandError(f"Could not read the snapshot: {type(exc).__name__}") from exc
            self.stdout.write(f"Register entries merged from the snapshot: {merged}")
        summary = reapply_user_erasures()
        self.stdout.write(
            "Anonymized {anonymized}, deleted {deleted}, failed {failed}.".format(
                **{key: len(value) for key, value in summary.items()}
            )
        )
        if summary["failed"]:
            raise CommandError(
                "Some erasures could not be re-applied (no replacement manager): "
                + ", ".join(str(user_id) for user_id in summary["failed"])
            )
