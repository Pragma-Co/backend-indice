import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.dataset import (
    CSV_FIELD_SIZE_LIMIT,
    MIN_EXAMPLES_PER_CLASS,
    DatasetValidationError,
    load_dataset,
)

SMALL_CATALOG = {
    "discipline": frozenset({"EST", "MAT"}),
    "document_type": frozenset({"DWG", "MEM"}),
    "area": frozenset({"EST", "SIS"}),
}
HEADER = "texto,disciplina,tipo,area"
FIRST_CLASS_LINE = "first document,EST,DWG,EST"
SECOND_CLASS_LINE = "second document,MAT,MEM,SIS"


def balanced_lines(per_class):
    return [FIRST_CLASS_LINE, SECOND_CLASS_LINE] * per_class


class LoadDatasetTests(SimpleTestCase):
    def write_csv(self, lines, header=HEADER, encoding="utf-8"):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "dataset.csv"
        path.write_bytes(("\n".join([header, *lines]) + "\n").encode(encoding))
        return path

    def load_with_errors(self, path):
        with self.assertRaises(DatasetValidationError) as raised:
            load_dataset(path, catalog=SMALL_CATALOG)
        return raised.exception.report

    def test_should_load_texts_and_labels_per_field(self):
        path = self.write_csv(balanced_lines(MIN_EXAMPLES_PER_CLASS))

        dataset = load_dataset(path, catalog=SMALL_CATALOG)

        self.assertEqual(len(dataset.texts), 2 * MIN_EXAMPLES_PER_CLASS)
        self.assertEqual(dataset.labels["discipline"][:2], ["EST", "MAT"])
        self.assertEqual(dataset.labels["document_type"][:2], ["DWG", "MEM"])
        self.assertEqual(dataset.labels["area"][:2], ["EST", "SIS"])
        self.assertEqual(dataset.report.warnings, [])

    def test_should_validate_against_default_catalog_when_none_is_given(self):
        path = self.write_csv([FIRST_CLASS_LINE] * 30 + ["document,XXX,DWG,EST"])

        with self.assertRaises(DatasetValidationError) as raised:
            load_dataset(path)

        self.assertIn(
            "discipline: label 'XXX' is not in the catalog (rows 31)",
            raised.exception.report.errors,
        )

    def test_should_count_examples_per_class(self):
        path = self.write_csv(balanced_lines(MIN_EXAMPLES_PER_CLASS))

        dataset = load_dataset(path, catalog=SMALL_CATALOG)

        self.assertEqual(
            dataset.report.class_counts["discipline"],
            {"EST": MIN_EXAMPLES_PER_CLASS, "MAT": MIN_EXAMPLES_PER_CLASS},
        )

    def test_should_read_file_with_utf8_bom(self):
        path = self.write_csv(balanced_lines(MIN_EXAMPLES_PER_CLASS), header="﻿" + HEADER)

        dataset = load_dataset(path, catalog=SMALL_CATALOG)

        self.assertEqual(len(dataset.texts), 2 * MIN_EXAMPLES_PER_CLASS)

    def test_should_reject_file_missing_required_columns(self):
        path = self.write_csv(["first document,EST"], header="texto,disciplina")

        report = self.load_with_errors(path)

        self.assertEqual(report.errors, ["Missing required columns: tipo, area"])

    def test_should_reject_file_that_is_not_utf8(self):
        path = self.write_csv(["ação,EST,DWG,EST"], encoding="latin-1")

        report = self.load_with_errors(path)

        self.assertEqual(report.errors, ["The file is not valid UTF-8"])

    def test_should_ignore_rows_with_empty_text_and_warn(self):
        lines = balanced_lines(MIN_EXAMPLES_PER_CLASS) + [",EST,DWG,EST", "   ,MAT,MEM,SIS"]
        path = self.write_csv(lines)

        dataset = load_dataset(path, catalog=SMALL_CATALOG)

        self.assertEqual(len(dataset.texts), 2 * MIN_EXAMPLES_PER_CLASS)
        self.assertIn("2 rows with empty text were ignored (rows 41, 42)", dataset.report.warnings)

    def test_should_reject_label_outside_the_catalog(self):
        path = self.write_csv(balanced_lines(MIN_EXAMPLES_PER_CLASS) + ["document,XXX,DWG,EST"])

        report = self.load_with_errors(path)

        self.assertEqual(report.errors, ["discipline: label 'XXX' is not in the catalog (rows 41)"])

    def test_should_reject_blank_label(self):
        path = self.write_csv(balanced_lines(MIN_EXAMPLES_PER_CLASS) + ["document,EST,,EST"])

        report = self.load_with_errors(path)

        self.assertEqual(report.errors, ["document_type: label '' is not in the catalog (rows 41)"])

    def test_should_warn_about_class_with_few_examples(self):
        path = self.write_csv([FIRST_CLASS_LINE] * 30 + [SECOND_CLASS_LINE] * 6)

        dataset = load_dataset(path, catalog=SMALL_CATALOG)

        self.assertIn(
            "discipline: class MAT has only 6 examples (recommended: 20)", dataset.report.warnings
        )

    def test_should_warn_about_catalog_class_without_examples(self):
        catalog = {**SMALL_CATALOG, "discipline": frozenset({"EST", "MAT", "FER"})}
        path = self.write_csv(balanced_lines(MIN_EXAMPLES_PER_CLASS))

        dataset = load_dataset(path, catalog=catalog)

        self.assertIn("discipline: class FER has no examples", dataset.report.warnings)

    def test_should_reject_class_with_single_example(self):
        path = self.write_csv([FIRST_CLASS_LINE] * 30 + [SECOND_CLASS_LINE])

        report = self.load_with_errors(path)

        self.assertIn(
            "discipline: class MAT has 1 example, at least 2 are needed for a stratified split",
            report.errors,
        )

    def test_should_reject_field_with_a_single_class(self):
        path = self.write_csv([FIRST_CLASS_LINE] * 30)

        report = self.load_with_errors(path)

        self.assertIn("discipline: at least 2 classes with examples are required", report.errors)

    def test_should_load_text_larger_than_default_csv_field_limit(self):
        long_text = "word " * 30000
        path = self.write_csv(balanced_lines(MIN_EXAMPLES_PER_CLASS) + [f"{long_text},EST,DWG,EST"])

        dataset = load_dataset(path, catalog=SMALL_CATALOG)

        self.assertEqual(len(dataset.texts[-1]), len(long_text))
        self.assertGreater(len(long_text), 131072)
        self.assertGreater(CSV_FIELD_SIZE_LIMIT, len(long_text))
