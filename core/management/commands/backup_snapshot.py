from django.core.management.base import BaseCommand, CommandError

from core.models.choices import BackupStatus, BackupTarget
from core.services.backup_service import run_backup

TARGETS = {
    "postgres": [BackupTarget.POSTGRES],
    "mongodb": [BackupTarget.MONGODB],
    "all": [BackupTarget.POSTGRES, BackupTarget.MONGODB],
}


class Command(BaseCommand):
    help = "Export an encrypted snapshot of PostgreSQL and/or MongoDB and record the run."

    def add_arguments(self, parser):
        parser.add_argument("--target", choices=sorted(TARGETS), default="all")
        parser.add_argument("--keep", type=int, default=None)

    def handle(self, *args, target, keep, **options):
        failed = []
        for item in TARGETS[target]:
            run = run_backup(item, keep=keep)
            outcome = run.destination if run.status == BackupStatus.SUCCEEDED else run.error
            self.stdout.write(f"{run.target}: {run.status} {outcome}")
            if run.status == BackupStatus.FAILED:
                failed.append(run.target)
        if failed:
            raise CommandError(f"Snapshot failed for {', '.join(failed)}; see backup_run.")
