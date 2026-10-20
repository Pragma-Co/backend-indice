from django.core.management.base import BaseCommand

from core.models import Document
from core.services.document_index_service import index_document


class Command(BaseCommand):
    help = "Index the normalized content and thematic tags of documents for full-text search."

    def add_arguments(self, parser):
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Only index documents that have never been indexed.",
        )

    def handle(self, *args, **options):
        documents = Document.objects.order_by("id")
        if options["missing_only"]:
            documents = documents.filter(indexed_content__isnull=True)

        indexed = 0
        failed = 0
        for document in documents.iterator():
            try:
                index_document(document)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"{document.code}: {type(exc).__name__}")
                continue
            indexed += 1

        self.stdout.write(self.style.SUCCESS(f"Indexed {indexed} documents, {failed} failed."))
