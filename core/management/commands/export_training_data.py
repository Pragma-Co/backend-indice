from django.conf import settings
from django.core.management.base import BaseCommand

from core.services.training_export_service import DEFAULT_EXTENSIONS, export_training_data


class Command(BaseCommand):
    help = "Export registered documents and their labels as a CSV plus a folder of files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=str(settings.BASE_DIR / "training_export"),
            help="Directory that receives documents.csv and the files folder.",
        )
        parser.add_argument(
            "--extensions",
            nargs="+",
            default=list(DEFAULT_EXTENSIONS),
            help="File extensions to export (default: pdf docx).",
        )

    def handle(self, *args, **options):
        result = export_training_data(options["output_dir"], options["extensions"])

        for storage_path in result.missing:
            self.stderr.write(self.style.WARNING(f"File not found on disk: {storage_path}"))
        self.stdout.write(
            self.style.SUCCESS(f"{result.exported} files exported to {options['output_dir']}.")
        )
