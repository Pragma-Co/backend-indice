import contextlib
import io
import tempfile
from pathlib import Path
from unittest import mock

import joblib
from django.test import SimpleTestCase

from classifier import train, vectorize
from classifier.training_run import StoredFeatures, run_training
from classifier.vector_store import VectorStore, vectorizer_version
from classifier.vectorize import fit_and_store
from core.tests.classifier_fixtures import keyword_dataset
from core.tests.test_classifier_train_command import write_dataset_csv
from core.tests.test_classifier_vector_store import FakeCollection


def run(command, *arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = command.main(list(arguments))
    return code, stdout.getvalue(), stderr.getvalue()


class VectorizeCommandTests(SimpleTestCase):
    def setUp(self):
        self.store = VectorStore(FakeCollection())
        self.enterContext(mock.patch.object(vectorize, "get_vector_store", lambda: self.store))
        self.enterContext(mock.patch.object(train, "get_vector_store", lambda: self.store))
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.csv = self.directory / "dataset.csv"
        self.model = self.directory / "model"
        write_dataset_csv(self.csv)

    def test_should_store_one_vector_per_document_and_save_the_vectorizer(self):
        code, output, _ = run(
            vectorize, "--csv", str(self.csv), "--output-dir", str(self.model)
        )

        vectorizer = joblib.load(self.model / "vectorizer.joblib")
        self.assertEqual(code, 0)
        self.assertIn("240 vectors stored", output)
        self.assertEqual(self.store.count(vectorizer_version(vectorizer)), 240)

    def test_should_train_from_the_stored_vectors(self):
        run(vectorize, "--csv", str(self.csv), "--output-dir", str(self.model))

        code, output, _ = run(
            train,
            "--csv",
            str(self.csv),
            "--output-dir",
            str(self.model),
            "--vectors-from-mongo",
        )

        self.assertEqual(code, 0)
        self.assertIn("240 vectors read from MongoDB", output)
        self.assertTrue((self.model / "model.pt").is_file())

    def test_should_refuse_to_train_from_mongo_before_vectorizing(self):
        code, _, errors = run(
            train,
            "--csv",
            str(self.csv),
            "--output-dir",
            str(self.model),
            "--vectors-from-mongo",
        )

        self.assertEqual(code, 1)
        self.assertIn("run python -m classifier.vectorize first", errors)

    def test_should_refuse_stored_vectors_of_another_version(self):
        run(vectorize, "--csv", str(self.csv), "--output-dir", str(self.model))
        run(
            vectorize,
            "--csv",
            str(self.csv),
            "--output-dir",
            str(self.directory / "other"),
            "--max-features",
            "5",
        )

        code, _, errors = run(
            train,
            "--csv",
            str(self.csv),
            "--output-dir",
            str(self.model),
            "--vectors-from-mongo",
        )

        self.assertEqual(code, 1)
        self.assertIn("240 of 240 texts have no stored vector", errors)


class StoredFeaturesTrainingTests(SimpleTestCase):
    def test_should_reproduce_the_in_memory_training_from_stored_vectors(self):
        dataset = keyword_dataset()
        store = VectorStore(FakeCollection())
        vectorizer, version, _ = fit_and_store(dataset, store, 20000, 42)
        stored = StoredFeatures(vectorizer, store.load(dataset.texts, version))

        in_memory = run_training(dataset)
        from_store = run_training(dataset, stored=stored)

        self.assertEqual(
            {name: e.f1_macro for name, e in in_memory.evaluations.items()},
            {name: e.f1_macro for name, e in from_store.evaluations.items()},
        )
