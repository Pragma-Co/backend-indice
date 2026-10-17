import csv
import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentArea,
    DocumentType,
    File,
    Project,
    Revision,
    User,
)
from core.services.training_export_service import export_training_data


class ExportTrainingDataTests(TestCase):
    def setUp(self):
        self.storage_dir = tempfile.mkdtemp()
        self.output_dir = Path(tempfile.mkdtemp()) / "export"
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.output_dir.parent, ignore_errors=True)
        override = override_settings(DOCUMENT_STORAGE_DIR=self.storage_dir)
        override.enable()
        self.addCleanup(override.disable)

        self.est = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.qua = Area.objects.create(acronym="QUA", name="Qualidade e Inspeção")
        self.user = User.objects.create_user(
            email="author@example.com", password="pw", name="Author", area=self.est
        )
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="ESP", name="Especificação")

    def _create_document(self, code, areas):
        document = Document.objects.create(
            code=code,
            title=f"Title {code}",
            description="Description",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.user,
            created_by=self.user,
        )
        for area in areas:
            DocumentArea.objects.create(document=document, area=area)
        return document

    def _attach_file(self, document, version, extension="pdf", hash_char="a", stored=True):
        revision, _ = Revision.objects.get_or_create(
            document=document, version=version, defaults={"author": self.user}
        )
        storage_path = f"documents/{document.code}/v{version}/{hash_char}.{extension}"
        if stored:
            full_path = Path(self.storage_dir) / storage_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(b"content " + hash_char.encode())
        return File.objects.create(
            revision=revision,
            original_name=f"original.{extension}",
            extension=extension,
            mime_type="application/octet-stream",
            size_bytes=10,
            sha256=hash_char * 64,
            storage_path=storage_path,
        )

    def _read_rows(self):
        with (self.output_dir / "documents.csv").open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_should_write_one_row_per_file_with_the_document_labels(self):
        document = self._create_document("AK-2100-EST-ESP-0001", [self.qua, self.est])
        self._attach_file(document, 1, hash_char="a")

        export_training_data(self.output_dir)

        row = self._read_rows()[0]
        self.assertEqual(row["document_code"], "AK-2100-EST-ESP-0001")
        self.assertEqual(row["project"], "AK-2100")
        self.assertEqual(row["discipline"], "EST")
        self.assertEqual(row["areas"], "EST;QUA")
        self.assertEqual(row["document_type"], "ESP")
        self.assertEqual(row["original_name"], "original.pdf")

    def test_should_copy_each_file_named_by_its_hash(self):
        document = self._create_document("AK-2100-EST-ESP-0001", [self.est])
        stored = self._attach_file(document, 1, hash_char="a")

        export_training_data(self.output_dir)

        row = self._read_rows()[0]
        self.assertEqual(row["file"], f"files/{stored.sha256}.pdf")
        self.assertTrue((self.output_dir / row["file"]).is_file())

    def test_should_export_only_the_latest_revision_of_a_document(self):
        document = self._create_document("AK-2100-EST-ESP-0001", [self.est])
        self._attach_file(document, 1, hash_char="a")
        self._attach_file(document, 2, hash_char="b")

        export_training_data(self.output_dir)

        rows = self._read_rows()
        self.assertEqual([row["revision_version"] for row in rows], ["2"])

    def test_should_skip_extensions_that_were_not_requested(self):
        document = self._create_document("AK-2100-EST-ESP-0001", [self.est])
        self._attach_file(document, 1, extension="pdf", hash_char="a")
        self._attach_file(document, 1, extension="png", hash_char="b")

        export_training_data(self.output_dir)

        self.assertEqual([row["original_name"] for row in self._read_rows()], ["original.pdf"])

    def test_should_report_files_missing_from_storage_and_skip_them(self):
        document = self._create_document("AK-2100-EST-ESP-0001", [self.est])
        missing = self._attach_file(document, 1, hash_char="a", stored=False)

        result = export_training_data(self.output_dir)

        self.assertEqual(result.missing, [missing.storage_path])
        self.assertEqual(result.exported, 0)
        self.assertEqual(self._read_rows(), [])

    def test_should_write_only_the_header_when_there_are_no_documents(self):
        result = export_training_data(self.output_dir)

        self.assertEqual(result.exported, 0)
        self.assertEqual(self._read_rows(), [])
