import shutil
import socket
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from classifier.catalog import FIELDS, load_catalog
from classifier.neural_training import TrainingConfig
from classifier.persistence import save_model
from classifier.prediction import Classifier
from classifier.training_run import run_training
from core.tests.classifier_fixtures import keyword_dataset


class ClassifierTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, root, True)
        dataset = keyword_dataset()
        run = run_training(dataset, TrainingConfig(max_epochs=60, patience=8))
        dataset_path = root / "dataset.csv"
        dataset_path.write_text("text,group\nfake,doc\n", encoding="utf-8")
        directory = save_model(
            run.trained,
            run.vectorizer,
            run.evaluations,
            dataset_path,
            load_catalog(),
            criteria_version="1",
            row_count=len(dataset.texts),
            output_dir=root / "model",
        )
        cls.classifier = Classifier(directory)

    def test_should_predict_the_three_fields_in_a_single_call(self):
        predictions = self.classifier.predict("voltage shall welding requirement document")

        self.assertEqual(list(predictions), list(FIELDS))

    def test_should_return_a_label_from_the_catalog_for_each_field(self):
        catalog = load_catalog()

        predictions = self.classifier.predict("bearing practice drawing requirement document")

        for name in FIELDS:
            self.assertIn(predictions[name].label, catalog[name])

    def test_should_return_a_confidence_between_zero_and_one(self):
        predictions = self.classifier.predict("alloy guidance sampling requirement document")

        for prediction in predictions.values():
            self.assertTrue(0.0 <= prediction.confidence <= 1.0)

    def test_should_recognize_the_signal_it_was_trained_on(self):
        predictions = self.classifier.predict("voltage shall welding voltage shall welding")

        self.assertEqual(predictions["discipline"].label, "ELECTRICAL")
        self.assertEqual(predictions["document_type"].label, "SPECIFICATION")
        self.assertEqual(predictions["area"].label, "OTHER_STAGE")

    def test_should_predict_without_opening_any_network_connection(self):
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
            predictions = self.classifier.predict("alloy practice drawing requirement document")

        self.assertEqual(list(predictions), list(FIELDS))

    def test_should_reject_an_empty_text(self):
        with self.assertRaises(ValueError):
            self.classifier.predict("   ")
