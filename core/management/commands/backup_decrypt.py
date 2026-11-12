from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.backup_service import (
    FILE_SUFFIX,
    BackupConfigurationError,
    BackupFileError,
    decrypt_snapshot,
)


class Command(BaseCommand):
    help = "Decrypt a snapshot produced by backup_snapshot into a plain JSON file."

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("--output", default=None)

    def handle(self, *args, source, output, **options):
        source_path = Path(source)
        if not source_path.is_file():
            raise CommandError(f"{source} does not exist.")
        default_name = source_path.name.removesuffix(FILE_SUFFIX) + ".json"
        destination = Path(output) if output else source_path.with_name(default_name)
        try:
            decrypt_snapshot(source_path, destination)
        except (BackupConfigurationError, BackupFileError) as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(f"Could not decrypt the snapshot: {type(exc).__name__}") from exc
        self.stdout.write(f"Decrypted to {destination}")
