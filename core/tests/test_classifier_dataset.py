import csv
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.catalog import load_catalog
from classifier.dataset import (
    CSV_COLUMNS,
    MIN_EXAMPLES_PER_CLASS,
    DatasetValidationError,
    load_dataset,
)

COLUMNS = list(CSV_COLUMNS.values())


def row(index: int, **overrides) -> dict:
    values = {
        "text": f"document {index}",
        "discipline": "MECHANICAL" if index % 2 else "ELECTRICAL",
        "document_type": "SPECIFICATION" if index % 2 else "STANDARD",
        "area": "DESIGN" if index % 2 else "OTHER_STAGE",
        "group": f"DOC-{index}",
    }
    return {**values, **overrides}


class LoadDatasetTests(SimpleTestCase):
    def write_csv(self, rows: list[dict], columns=COLUMNS) -> Path:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = directory / "dataset.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_should_load_texts_labels_and_groups(self):
        path = self.write_csv([row(index) for index in range(1, 5)])

        dataset = load_dataset(path, load_catalog())

        self.assertEqual(len(dataset.texts), 4)
        self.assertEqual(dataset.groups, ["DOC-1", "DOC-2", "DOC-3", "DOC-4"])
        self.assertEqual(dataset.labels["document_type"][:2], ["SPECIFICATION", "STANDARD"])

    def test_should_fail_on_a_label_outside_the_catalog_naming_field_label_and_rows(self):
        rows = [row(index) for index in range(1, 7)]
        rows[2] = row(3, area="ASSEMBLY")
        path = self.write_csv(rows)

        with self.assertRaises(DatasetValidationError) as raised:
            load_dataset(path, load_catalog())

        self.assertEqual(
            raised.exception.report.errors,
            ["area: label 'ASSEMBLY' is not in the catalog (rows 3)"],
        )

    def test_should_ignore_rows_with_empty_text_and_warn(self):
        rows = [row(index) for index in range(1, 7)]
        rows[1] = row(2, text="   ")
        path = self.write_csv(rows)

        dataset = load_dataset(path, load_catalog())

        self.assertEqual(len(dataset.texts), 5)
        self.assertIn("1 rows with empty text were ignored (rows 2)", dataset.report.warnings)

    def test_should_fail_when_a_row_has_no_group(self):
        rows = [row(index) for index in range(1, 7)]
        rows[1] = row(2, group=" ")
        path = self.write_csv(rows)

        with self.assertRaises(DatasetValidationError) as raised:
            load_dataset(path, load_catalog())

        self.assertIn("1 rows have no group (rows 2)", raised.exception.report.errors)

    def test_should_fail_when_a_required_column_is_missing(self):
        columns = [name for name in COLUMNS if name != "group"]
        path = self.write_csv([row(1)], columns=columns)

        with self.assertRaises(DatasetValidationError) as raised:
            load_dataset(path, load_catalog())

        self.assertEqual(raised.exception.report.errors, ["Missing required columns: group"])

    def test_should_warn_about_a_class_with_fewer_examples_than_recommended(self):
        path = self.write_csv([row(index) for index in range(1, 5)])

        dataset = load_dataset(path, load_catalog())

        self.assertIn(
            f"document_type: class STANDARD has only 2 examples "
            f"(recommended: {MIN_EXAMPLES_PER_CLASS})",
            dataset.report.warnings,
        )

    def test_should_fail_when_a_class_has_a_single_example(self):
        rows = [row(index) for index in range(1, 5)]
        rows.append(row(5, document_type="HANDBOOK"))
        path = self.write_csv(rows)

        with self.assertRaises(DatasetValidationError) as raised:
            load_dataset(path, load_catalog())

        self.assertTrue(
            any("class HANDBOOK has 1 example" in error for error in raised.exception.report.errors)
        )
