import contextlib
import io
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.predict import main
from classifier.train import main as train_main
from core.tests.test_classifier_train_command import write_dataset_csv


class PredictCommandTests(SimpleTestCase):
    def run_command(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_should_print_label_and_confidence_per_field_for_a_text_file(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        write_dataset_csv(directory / "dataset.csv")
        with contextlib.redirect_stdout(io.StringIO()):
            train_main(
                ["--csv", str(directory / "dataset.csv"), "--output-dir", str(directory / "model")]
            )
        (directory / "doc.txt").write_text("voltage shall welding document", encoding="utf-8")

        code, output, _ = self.run_command(
            "--file", str(directory / "doc.txt"), "--model-dir", str(directory / "model")
        )

        self.assertEqual(code, 0)
        self.assertIn("doc.txt: 30 characters", output)
        for field_name in ("discipline", "document_type", "area"):
            self.assertRegex(output, rf"{field_name}\s+\S+\s+\d+\.\d%")

    def test_should_fail_when_the_file_does_not_exist(self):
        code, _, errors = self.run_command("--file", "missing.pdf")

        self.assertEqual(code, 1)
        self.assertIn("missing.pdf not found", errors)
