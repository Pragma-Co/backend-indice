import contextlib
import csv
import io
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.dataset import CSV_COLUMNS
from classifier.prediction import Classifier
from classifier.train import main
from core.tests.classifier_fixtures import keyword_dataset


def write_dataset_csv(path: Path, mutate=None) -> None:
    dataset = keyword_dataset()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS.values()))
        writer.writeheader()
        for index, text in enumerate(dataset.texts):
            row = {
                "text": text,
                "discipline": dataset.labels["discipline"][index],
                "document_type": dataset.labels["document_type"][index],
                "area": dataset.labels["area"][index],
                "group": dataset.groups[index],
            }
            writer.writerow(mutate(row) if mutate else row)


class TrainCommandTests(SimpleTestCase):
    def run_command(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_should_train_evaluate_save_and_leave_a_loadable_model(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        write_dataset_csv(directory / "dataset.csv")

        code, output, _ = self.run_command(
            "--csv", str(directory / "dataset.csv"), "--output-dir", str(directory / "model")
        )

        self.assertEqual(code, 0)
        for field_name in ("discipline", "document_type", "area"):
            self.assertIn(f"== {field_name} (trained on", output)
        prediction = Classifier(directory / "model").predict("voltage shall welding document")
        self.assertEqual(set(prediction), {"discipline", "document_type", "area"})

    def test_should_report_labels_outside_the_catalog_and_exit_with_an_error(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        write_dataset_csv(directory / "dataset.csv", mutate=lambda row: {**row, "area": "OTHER"})

        code, _, errors = self.run_command(
            "--csv", str(directory / "dataset.csv"), "--output-dir", str(directory / "model")
        )

        self.assertEqual(code, 1)
        self.assertIn("area: label 'OTHER' is not in the catalog", errors)
        self.assertFalse((directory / "model").exists())
