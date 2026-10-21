import numpy as np
from django.test import SimpleTestCase
from scipy.sparse import csr_matrix

from classifier.tfidf_input import build_vectorizer
from classifier.vector_store import (
    VectorStore,
    VectorStoreError,
    text_sha256,
    vectorizer_version,
)


class FakeCollection:
    def __init__(self):
        self.records = {}

    def replace_one(self, selector, record, upsert=False):
        self.records[selector["_id"]] = dict(record)

    def find(self, selector):
        keys = selector["_id"]["$in"]
        return [dict(self.records[key]) for key in keys if key in self.records]

    def count_documents(self, selector):
        return sum(
            1
            for record in self.records.values()
            if record["vectorizer_version"] == selector["vectorizer_version"]
        )


TEXTS = ["steel plate thickness", "copper wire insulation", "paint primer coating"]


def fitted_vectorizer(texts=TEXTS, max_features=20000):
    vectorizer = build_vectorizer(max_features)
    vectorizer.min_df = 1
    return vectorizer, vectorizer.fit_transform(texts)


class VectorStoreTests(SimpleTestCase):
    def test_should_return_the_same_sparse_vectors_it_stored(self):
        vectorizer, features = fitted_vectorizer()
        store = VectorStore(FakeCollection())
        version = vectorizer_version(vectorizer)

        saved = store.save_all(TEXTS, features, version)
        loaded = store.load(TEXTS, version)

        self.assertEqual(saved, 3)
        self.assertEqual(loaded.shape, features.shape)
        np.testing.assert_allclose(loaded.toarray(), features.toarray())

    def test_should_key_records_by_the_text_fingerprint(self):
        vectorizer, features = fitted_vectorizer()
        collection = FakeCollection()

        VectorStore(collection).save_all(TEXTS, features, vectorizer_version(vectorizer))

        self.assertEqual(set(collection.records), {text_sha256(text) for text in TEXTS})

    def test_should_refuse_vectors_of_another_vectorizer_version(self):
        vectorizer, features = fitted_vectorizer()
        store = VectorStore(FakeCollection())
        store.save_all(TEXTS, features, "old-version")

        with self.assertRaisesMessage(VectorStoreError, "3 of 3 texts have no stored vector"):
            store.load(TEXTS, vectorizer_version(vectorizer))

    def test_should_count_the_texts_without_a_vector(self):
        vectorizer, features = fitted_vectorizer()
        store = VectorStore(FakeCollection())
        version = vectorizer_version(vectorizer)
        store.save_all(TEXTS[:2], features[:2], version)

        with self.assertRaisesMessage(VectorStoreError, "1 of 3 texts"):
            store.load(TEXTS, version)

    def test_should_keep_the_order_of_the_requested_texts(self):
        vectorizer, features = fitted_vectorizer()
        store = VectorStore(FakeCollection())
        version = vectorizer_version(vectorizer)
        store.save_all(TEXTS, features, version)

        loaded = store.load(list(reversed(TEXTS)), version)

        np.testing.assert_allclose(loaded.toarray(), features.toarray()[::-1])

    def test_should_refuse_a_vector_count_different_from_the_text_count(self):
        store = VectorStore(FakeCollection())

        with self.assertRaisesMessage(VectorStoreError, "3 texts for 2 vectors"):
            store.save_all(TEXTS, csr_matrix(np.zeros((2, 4))), "v")


class VectorizerVersionTests(SimpleTestCase):
    def test_should_give_the_same_version_for_the_same_fit(self):
        first, _ = fitted_vectorizer()
        second, _ = fitted_vectorizer()

        self.assertEqual(vectorizer_version(first), vectorizer_version(second))

    def test_should_change_the_version_when_the_vocabulary_changes(self):
        first, _ = fitted_vectorizer()
        second, _ = fitted_vectorizer(TEXTS + ["rubber gasket seal"])

        self.assertNotEqual(vectorizer_version(first), vectorizer_version(second))

    def test_should_change_the_version_when_max_features_changes(self):
        first, _ = fitted_vectorizer(max_features=20000)
        second, _ = fitted_vectorizer(max_features=4)

        self.assertNotEqual(vectorizer_version(first), vectorizer_version(second))
