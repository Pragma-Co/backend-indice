import contextlib
import csv
import io
import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.catalog import load_area_groups
from scripts.dataset.area_review import (
    EXCERPT_CHARS,
    build_review_rows,
    compute_agreement,
    draw_sample,
    main,
)

GROUPS = load_area_groups()


def dataset_rows(count: int = 100) -> list[dict]:
    stages = ["DESIGN", "MATERIALS", "PROCESSING", "INSPECTION_TEST"]
    return [
        {"document_id": f"DOC-{index}", "text": "x" * 3000, "area": stages[index % len(stages)]}
        for index in range(count)
    ]


class SampleTests(SimpleTestCase):
    def test_should_draw_the_same_sample_for_the_same_seed(self):
        rows = dataset_rows()

        self.assertEqual(draw_sample(rows, 20, seed=1), draw_sample(rows, 20, seed=1))

    def test_should_never_ask_for_more_documents_than_exist(self):
        self.assertEqual(len(draw_sample(dataset_rows(5), 60)), 5)

    def test_should_hide_the_ai_label_and_limit_the_excerpt_in_the_review_sheet(self):
        sample = draw_sample(dataset_rows(), 3)

        sheet = build_review_rows(sample, {"DOC-1": "A title"})

        for row in sheet:
            self.assertNotIn("area", row)
            self.assertEqual(len(row["excerpt"]), EXCERPT_CHARS)
            self.assertEqual(row["human_stage"], "")


class AgreementTests(SimpleTestCase):
    def review(self, labels: dict[str, str]) -> list[dict]:
        return [{"document_id": key, "human_stage": value} for key, value in labels.items()]

    def test_should_report_the_rate_and_the_sample_size(self):
        rows = dataset_rows(4)
        human = {"DOC-0": "DESIGN", "DOC-1": "MATERIALS", "DOC-2": "DESIGN", "DOC-3": "INSPECTION_TEST"}

        result = compute_agreement(rows, self.review(human), GROUPS)

        self.assertEqual(result["sample_size"], 4)
        self.assertAlmostEqual(result["rate"], 0.75)

    def test_should_count_two_different_rare_stages_as_agreement_on_the_area_class(self):
        rows = [{"document_id": "DOC-0", "text": "t", "area": "OTHER_STAGE", "area_stage": "PROCESSING"}]

        result = compute_agreement(rows, self.review({"DOC-0": "INSPECTION_TEST"}), GROUPS)

        self.assertEqual(result["rate"], 1.0)
        self.assertEqual(result["rate_fine"], 0.0)

    def test_should_not_count_a_rare_stage_against_a_main_class_as_agreement(self):
        rows = [{"document_id": "DOC-0", "text": "t", "area": "OTHER_STAGE", "area_stage": "PROCESSING"}]

        result = compute_agreement(rows, self.review({"DOC-0": "DESIGN"}), GROUPS)

        self.assertEqual((result["rate"], result["rate_fine"]), (0.0, 0.0))
        self.assertEqual(result["by_area_class"]["OTHER_STAGE"], {"compared": 1, "agreed": 0})

    def test_should_read_the_stage_from_the_area_column_in_files_made_before_the_grouping(self):
        rows = [{"document_id": "DOC-0", "text": "t", "area": "PROCESSING"}]

        result = compute_agreement(rows, self.review({"DOC-0": "PROCESSING"}), GROUPS)

        self.assertEqual(result["rate_fine"], 1.0)

    def test_should_break_the_result_down_by_the_ai_label(self):
        rows = dataset_rows(4)
        human = {"DOC-0": "DESIGN", "DOC-1": "MATERIALS", "DOC-2": "DESIGN", "DOC-3": "INSPECTION_TEST"}

        result = compute_agreement(rows, self.review(human), GROUPS)

        self.assertEqual(result["by_ai_label"]["PROCESSING"], {"compared": 1, "agreed": 0})

    def test_should_ignore_rows_the_person_left_blank_or_filled_with_an_unknown_stage(self):
        rows = dataset_rows(3)
        human = {"DOC-0": "DESIGN", "DOC-1": "", "DOC-2": "ASSEMBLY"}

        result = compute_agreement(rows, self.review(human), GROUPS)

        self.assertEqual(result["sample_size"], 1)
        self.assertEqual(result["ignored_rows"], 2)

    def test_should_return_zero_when_nothing_was_reviewed(self):
        result = compute_agreement(dataset_rows(2), self.review({"DOC-0": ""}), GROUPS)

        self.assertEqual((result["rate"], result["sample_size"]), (0.0, 0))


class CommandTests(SimpleTestCase):
    def run_command(self, *arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = main(list(arguments))
        return code, buffer.getvalue()

    def test_should_write_the_sheet_and_then_report_the_agreement(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        dataset = directory / "dataset.csv"
        with dataset.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["document_id", "text", "area"])
            writer.writeheader()
            writer.writerows(dataset_rows(10))
        sheet = directory / "review.csv"

        code, output = self.run_command(
            "sample", "--dataset", str(dataset), "--metadata", str(directory / "none.jsonl"),
            "--output", str(sheet), "--size", "4",
        )
        rows = list(csv.DictReader(sheet.open(encoding="utf-8-sig", newline="")))
        ai = {row["document_id"]: row["area"] for row in dataset_rows(10)}
        with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows({**row, "human_stage": ai[row["document_id"]]} for row in rows)
        agreement_file = directory / "agreement.json"
        second_code, second_output = self.run_command(
            "agreement", "--dataset", str(dataset), "--review", str(sheet),
            "--output", str(agreement_file),
        )

        self.assertEqual((code, second_code), (0, 0))
        self.assertIn("4 documents to review", output)
        self.assertIn("agreement with human: 100.0% on the area classes, 100.0% on the six stages, over 4 documents", second_output)
        self.assertEqual(json.loads(agreement_file.read_text())["sample_size"], 4)

    def test_should_draw_a_fresh_sample_that_skips_the_documents_already_reviewed(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        dataset, first, second = (directory / name for name in ("d.csv", "a.csv", "b.csv"))
        with dataset.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["document_id", "text", "area"])
            writer.writeheader()
            writer.writerows(dataset_rows(40))
        self.run_command(
            "sample", "--dataset", str(dataset), "--metadata", str(directory / "none"),
            "--output", str(first), "--size", "15",
        )

        code, _ = self.run_command(
            "sample", "--dataset", str(dataset), "--metadata", str(directory / "none"),
            "--output", str(second), "--size", "15", "--seed", "7", "--exclude-from", str(first),
        )

        def ids(path):
            return {row["document_id"] for row in csv.DictReader(path.open(encoding="utf-8-sig"))}

        self.assertEqual(code, 0)
        self.assertEqual(len(ids(second)), 15)
        self.assertEqual(ids(first) & ids(second), set())

    def test_should_record_who_filled_the_sheet_when_it_was_not_a_person(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        dataset, sheet = directory / "dataset.csv", directory / "review.csv"
        with dataset.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["document_id", "text", "area"])
            writer.writeheader()
            writer.writerows(dataset_rows(2))
        with sheet.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["document_id", "human_stage"])
            writer.writeheader()
            writer.writerows(
                [{"document_id": "DOC-0", "human_stage": "DESIGN"},
                 {"document_id": "DOC-1", "human_stage": "DESIGN"}]
            )
        agreement_file = directory / "agreement.json"

        _, output = self.run_command(
            "agreement", "--dataset", str(dataset), "--review", str(sheet),
            "--output", str(agreement_file), "--reviewer", "reference-model",
        )

        self.assertIn("agreement with reference-model: 50.0%", output)
        self.assertEqual(json.loads(agreement_file.read_text())["reviewer"], "reference-model")
