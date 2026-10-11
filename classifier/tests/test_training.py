from collections import Counter
from itertools import combinations

from django.test import SimpleTestCase

from classifier.pipeline import build_pipeline
from classifier.text_preprocessing import preprocess_for_llm
from classifier.training import TrainingError, train_field

STRUCTURE_WORDS = ["rivet", "fuselage", "frame", "skin", "stringer", "panel"]
HYDRAULIC_WORDS = ["hydraulic", "pump", "valve", "pressure", "actuator", "fluid"]


def synthetic_texts(words, count):
    return [" ".join(combination) for combination in list(combinations(words, 3))[:count]]


def two_class_corpus(per_class):
    texts = synthetic_texts(STRUCTURE_WORDS, per_class) + synthetic_texts(
        HYDRAULIC_WORDS, per_class
    )
    labels = ["EST"] * per_class + ["HID"] * per_class
    return texts, labels


class BuildPipelineTests(SimpleTestCase):
    def test_should_chain_tfidf_and_logistic_regression(self):
        pipeline = build_pipeline()

        self.assertEqual([name for name, _ in pipeline.steps], ["tfidf", "classifier"])

    def test_should_preprocess_inside_the_vectorizer(self):
        pipeline = build_pipeline()

        self.assertIs(pipeline.named_steps["tfidf"].preprocessor, preprocess_for_llm)


class TrainFieldTests(SimpleTestCase):
    def test_should_split_with_every_class_in_train_and_test(self):
        texts, labels = two_class_corpus(20)

        trained = train_field("discipline", texts, labels)

        self.assertEqual(trained.train_size, 32)
        self.assertEqual(Counter(trained.test_labels), {"EST": 4, "HID": 4})

    def test_should_produce_the_same_split_for_the_same_random_state(self):
        texts, labels = two_class_corpus(20)

        first = train_field("discipline", texts, labels)
        second = train_field("discipline", texts, labels)

        self.assertEqual(first.test_texts, second.test_texts)

    def test_should_change_the_split_for_a_different_random_state(self):
        texts, labels = two_class_corpus(20)

        first = train_field("discipline", texts, labels, random_state=1)
        second = train_field("discipline", texts, labels, random_state=2)

        self.assertNotEqual(first.test_texts, second.test_texts)

    def test_should_fit_a_pipeline_that_predicts_labels_with_probabilities(self):
        texts, labels = two_class_corpus(20)

        trained = train_field("discipline", texts, labels)

        self.assertEqual(list(trained.pipeline.predict(trained.test_texts)), trained.test_labels)
        probabilities = trained.pipeline.predict_proba(trained.test_texts[:1])[0]
        self.assertAlmostEqual(probabilities.sum(), 1.0)
        self.assertEqual(list(trained.pipeline.classes_), ["EST", "HID"])

    def test_should_report_a_clear_error_when_the_split_is_impossible(self):
        texts, labels = two_class_corpus(1)

        with self.assertRaises(TrainingError) as raised:
            train_field("discipline", texts, labels)

        self.assertIn("discipline: could not split the dataset", str(raised.exception))
