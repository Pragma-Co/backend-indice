import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.catalog import FIELDS
from classifier.comparison import (
    BASELINE_NAME,
    NETWORK_NAME,
    AreaAgreement,
    format_f1_table,
    format_report,
    load_area_agreement,
    run_comparison,
)
from classifier.evaluation import evaluate_fields
from classifier.neural_training import TrainingConfig
from core.tests.classifier_fixtures import keyword_dataset

SMALL_CONFIG = TrainingConfig(max_epochs=40, patience=5)


class RunComparisonTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dataset = keyword_dataset()
        cls.report = run_comparison(cls.dataset, SMALL_CONFIG)

    def test_should_evaluate_the_baseline_and_the_network_on_every_field(self):
        self.assertEqual(list(self.report.setups), [BASELINE_NAME, NETWORK_NAME])
        for evaluations in self.report.setups.values():
            self.assertEqual(list(evaluations), list(FIELDS))

    def test_should_score_both_setups_on_the_same_test_documents(self):
        supports = {
            name: {evaluations[field].support for field in FIELDS}
            for name, evaluations in self.report.setups.items()
        }

        self.assertEqual(supports[BASELINE_NAME], supports[NETWORK_NAME])
        self.assertEqual(supports[NETWORK_NAME], {self.report.test_size})

    def test_should_list_one_row_per_field_and_the_mean_in_the_f1_table(self):
        table = format_f1_table(self.report)

        for label in (*FIELDS, "mean", BASELINE_NAME, NETWORK_NAME):
            self.assertIn(label, table)
        self.assertIn(f"macro F1 on {self.report.test_size} test documents", table)

    def test_should_add_extra_setups_to_the_same_table(self):
        def perfect_setup(dataset, split, classes):
            expected = {
                name: [dataset.labels[name][index] for index in split.test] for name in FIELDS
            }
            return evaluate_fields(expected, expected, classes)

        report = run_comparison(
            self.dataset, SMALL_CONFIG, extra_setups={"C: stand-in": perfect_setup}
        )

        self.assertEqual(list(report.setups)[-1], "C: stand-in")
        self.assertIn("1.000", format_f1_table(report))

    def test_should_report_the_area_agreement_when_it_is_known(self):
        report = run_comparison(
            self.dataset, SMALL_CONFIG, area_agreements=[AreaAgreement(rate=0.8, sample_size=50)]
        )

        text = format_report(report)

        self.assertIn("agrees with the human sample on 80.0% of 50 documents", text)

    def test_should_list_every_agreement_with_its_label_and_fine_rate(self):
        agreements = [
            AreaAgreement(rate=0.88, sample_size=60, reviewer="fable", label="criteria v1", rate_fine=0.87),
            AreaAgreement(rate=0.9, sample_size=30, reviewer="fable", label="hold-out, criteria v2"),
        ]
        report = run_comparison(self.dataset, SMALL_CONFIG, area_agreements=agreements)

        text = format_report(report)

        self.assertIn("fable sample, criteria v1 on 88.0% of 60 documents (87.0% on the six stages)", text)
        self.assertIn("fable sample, hold-out, criteria v2 on 90.0% of 30 documents;", text)

    def test_should_parse_a_labelled_agreement_file(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = directory / "a.json"
        path.write_text(json.dumps({"rate": 0.5, "rate_fine": 0.4, "sample_size": 10, "reviewer": "x"}))

        agreement = load_area_agreement(f"criteria v2={path}")

        self.assertEqual((agreement.label, agreement.rate_fine, agreement.reviewer), ("criteria v2", 0.4, "x"))
        self.assertEqual(load_area_agreement(str(path)).label, "")

    def test_should_name_the_reviewer_when_it_was_not_a_person(self):
        agreement = AreaAgreement(rate=0.7, sample_size=60, reviewer="reference-model")
        report = run_comparison(self.dataset, SMALL_CONFIG, area_agreements=[agreement])

        text = format_report(report)

        self.assertIn("agrees with the reference-model sample on 70.0% of 60 documents", text)

    def test_should_include_a_confusion_matrix_for_each_setup_and_field(self):
        text = format_report(self.report)

        self.assertIn(f"{NETWORK_NAME} | area", text)
        self.assertIn(f"{BASELINE_NAME} | document_type", text)
