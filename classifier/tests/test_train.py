import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from django.test import SimpleTestCase

from classifier.tests.test_training import HYDRAULIC_WORDS, STRUCTURE_WORDS, synthetic_texts
from classifier.train import main

HEADER = "texto,disciplina,tipo,area"


def dataset_lines():
    structure = [f"{text},EST,DWG,EST" for text in synthetic_texts(STRUCTURE_WORDS, 20)]
    hydraulic = [f"{text},HID,MEM,SIS" for text in synthetic_texts(HYDRAULIC_WORDS, 20)]
    return structure + hydraulic


class TrainCommandTests(SimpleTestCase):
    def write_csv(self, lines):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "dataset.csv"
        path.write_text("\n".join([HEADER, *lines]) + "\n", encoding="utf-8")
        return str(path)

    def run_main(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_should_train_every_field_and_report_split_sizes(self):
        path = self.write_csv(dataset_lines())

        status, stdout, _ = self.run_main(["--csv", path])

        self.assertEqual(status, 0)
        self.assertIn("40 usable documents out of 40 rows", stdout)
        self.assertIn("discipline: trained on 32, held out 8", stdout)
        self.assertIn("document_type: trained on 32, held out 8", stdout)
        self.assertIn("area: trained on 32, held out 8", stdout)

    def test_should_exit_with_error_when_the_dataset_is_invalid(self):
        path = self.write_csv(dataset_lines() + ["document,XXX,DWG,EST"])

        status, _, stderr = self.run_main(["--csv", path])

        self.assertEqual(status, 1)
        self.assertIn("ERROR: discipline: label 'XXX' is not in the catalog", stderr)

    def test_should_print_dataset_warnings_without_failing(self):
        path = self.write_csv(dataset_lines())

        status, _, stderr = self.run_main(["--csv", path])

        self.assertEqual(status, 0)
        self.assertIn("WARNING: discipline: class AER has no examples", stderr)
