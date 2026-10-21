from django.test import SimpleTestCase

from classifier.evaluation import evaluate_fields, evaluate_predictions, format_evaluation

LABELS = ["A", "B", "C"]
EXPECTED = ["A", "A", "A", "B", "B", "C"]
PREDICTED = ["A", "A", "B", "B", "B", "A"]


class EvaluatePredictionsTests(SimpleTestCase):
    def test_should_compute_precision_recall_and_f1_per_class(self):
        evaluation = evaluate_predictions("area", EXPECTED, PREDICTED, LABELS)

        report = evaluation.report
        self.assertAlmostEqual(report["A"]["precision"], 2 / 3)
        self.assertAlmostEqual(report["A"]["recall"], 2 / 3)
        self.assertAlmostEqual(report["B"]["precision"], 2 / 3)
        self.assertAlmostEqual(report["B"]["recall"], 1.0)
        self.assertAlmostEqual(report["B"]["f1-score"], 0.8)
        self.assertEqual(report["C"]["f1-score"], 0.0)

    def test_should_average_the_class_f1_scores_into_the_macro_f1(self):
        evaluation = evaluate_predictions("area", EXPECTED, PREDICTED, LABELS)

        self.assertAlmostEqual(evaluation.f1_macro, (2 / 3 + 0.8 + 0.0) / 3)
        self.assertAlmostEqual(evaluation.accuracy, 4 / 6)

    def test_should_build_the_confusion_matrix_with_true_labels_in_rows(self):
        evaluation = evaluate_predictions("area", EXPECTED, PREDICTED, LABELS)

        self.assertEqual(evaluation.confusion_matrix, [[2, 1, 0], [0, 2, 0], [1, 0, 0]])

    def test_should_keep_a_class_with_no_predictions_in_the_report(self):
        evaluation = evaluate_predictions("area", ["A", "B"], ["A", "A"], LABELS)

        self.assertEqual(evaluation.report["C"]["support"], 0)
        self.assertEqual(evaluation.labels, LABELS)

    def test_should_evaluate_every_field_from_dictionaries(self):
        expected = {"discipline": ["A", "B"], "area": ["A", "A"]}
        predicted = {"discipline": ["A", "B"], "area": ["A", "B"]}
        classes = {"discipline": ["A", "B"], "area": ["A", "B"]}

        evaluations = evaluate_fields(expected, predicted, classes)

        self.assertEqual(set(evaluations), {"discipline", "area"})
        self.assertEqual(evaluations["discipline"].accuracy, 1.0)
        self.assertEqual(evaluations["area"].accuracy, 0.5)

    def test_should_print_the_macro_f1_and_the_confusion_matrix(self):
        evaluation = evaluate_predictions("area", EXPECTED, PREDICTED, LABELS)

        text = format_evaluation(evaluation, train_size=20)

        self.assertIn("== area (trained on 20, tested on 6) ==", text)
        self.assertIn("f1 macro: 0.489", text)
        self.assertIn("confusion matrix", text)
