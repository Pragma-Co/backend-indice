import json
import shutil
import tempfile
from pathlib import Path

import torch
from django.test import SimpleTestCase

from classifier.catalog import load_catalog
from classifier.neural_training import TrainingConfig, to_tensor
from classifier.persistence import (
    METADATA_FILENAME,
    MODEL_FILENAME,
    ArtifactsError,
    load_model,
    save_model,
)
from classifier.training_run import run_training
from core.tests.classifier_fixtures import keyword_dataset

SMALL_CONFIG = TrainingConfig(max_epochs=40, patience=5)


class PersistenceTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, root, True)
        cls.dataset = keyword_dataset()
        cls.training = run_training(cls.dataset, SMALL_CONFIG)
        cls.dataset_path = root / "dataset.csv"
        cls.dataset_path.write_text("text,group\nfake,doc\n", encoding="utf-8")
        cls.root = root

    def save(self, name: str = "model") -> Path:
        directory = self.root / name
        return save_model(
            self.training.trained,
            self.training.vectorizer,
            self.training.evaluations,
            self.dataset_path,
            load_catalog(),
            criteria_version="1",
            row_count=len(self.dataset.texts),
            output_dir=directory,
        )

    def test_should_save_the_model_vectorizer_and_metadata(self):
        directory = self.save("saved")

        names = sorted(path.name for path in directory.iterdir())

        self.assertEqual(names, [METADATA_FILENAME, MODEL_FILENAME, "vectorizer.joblib"])

    def test_should_record_what_is_needed_to_reproduce_the_training(self):
        directory = self.save("metadata")

        metadata = json.loads((directory / METADATA_FILENAME).read_text(encoding="utf-8"))

        for key in ("created_at", "torch_version", "dataset_sha256", "text_handling_sha256"):
            self.assertTrue(metadata[key])
        self.assertEqual(metadata["criteria_version"], "1")
        self.assertEqual(metadata["input_representation"], "tfidf")
        self.assertEqual(set(metadata["fields"]), {"discipline", "document_type", "area"})
        self.assertIn("f1_macro", metadata["fields"]["area"])
        self.assertIn("random_state", metadata["split"])

    def test_should_reload_a_model_that_predicts_like_the_trained_one(self):
        directory = self.save("reload")
        features = to_tensor(self.training.vectorizer.transform(self.dataset.texts[:10]))

        loaded = load_model(directory)

        expected = self.training.trained.network.predict_probabilities(features)
        actual = loaded.network.predict_probabilities(
            to_tensor(loaded.vectorizer.transform(self.dataset.texts[:10]))
        )
        for name in expected:
            self.assertTrue(torch.allclose(expected[name], actual[name]))

    def test_should_name_the_missing_model_file(self):
        directory = self.save("missing-model")
        (directory / MODEL_FILENAME).unlink()

        with self.assertRaisesMessage(ArtifactsError, MODEL_FILENAME):
            load_model(directory)

    def test_should_name_the_missing_metadata_file(self):
        directory = self.save("missing-metadata")
        (directory / METADATA_FILENAME).unlink()

        with self.assertRaisesMessage(ArtifactsError, METADATA_FILENAME):
            load_model(directory)

    def test_should_refuse_a_model_trained_with_a_different_text_handling(self):
        directory = self.save("other-handling")
        metadata_path = directory / METADATA_FILENAME
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["text_handling_sha256"] = "0" * 64
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        with self.assertRaisesMessage(ArtifactsError, "retrain"):
            load_model(directory)

    def test_should_refuse_files_left_by_the_previous_per_field_trainer(self):
        directory = self.root / "old-format"
        directory.mkdir()
        (directory / METADATA_FILENAME).write_text(json.dumps({"rows": 478}), encoding="utf-8")

        with self.assertRaisesMessage(ArtifactsError, "retrain"):
            load_model(directory)
