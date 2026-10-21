from django.test import SimpleTestCase

from classifier.tfidf_input import build_vectorizer

TRAINING_TEXTS = [
    "Aircraft hydraulic pump assembly requirements and acceptance testing.",
    "Aircraft hydraulic hose assembly requirements for fluid lines.",
    "Electrical connector requirements for aircraft wiring and cable assembly.",
    "Electrical wire and cable requirements for power distribution equipment.",
    "Paint coating requirements for aircraft metal surfaces and finishing.",
    "Paint primer coating requirements for metal surfaces and corrosion protection.",
]


class TfidfInputTests(SimpleTestCase):
    def test_should_produce_the_same_dimension_for_training_and_new_texts(self):
        vectorizer = build_vectorizer()

        training = vectorizer.fit_transform(TRAINING_TEXTS)
        unseen = vectorizer.transform(["A brand new document about hydraulic pump requirements."])

        self.assertEqual(training.shape[1], unseen.shape[1])
        self.assertGreater(unseen.nnz, 0)

    def test_should_never_exceed_the_feature_cap(self):
        vectorizer = build_vectorizer(max_features=5)

        matrix = vectorizer.fit_transform(TRAINING_TEXTS)

        self.assertLessEqual(matrix.shape[1], 5)

    def test_should_only_keep_terms_that_appear_in_at_least_two_documents(self):
        vectorizer = build_vectorizer()

        vectorizer.fit(TRAINING_TEXTS)

        self.assertNotIn("pump", vectorizer.vocabulary_)
        self.assertIn("requirement", vectorizer.vocabulary_)

    def test_should_drop_tokens_that_mix_digits_and_letters_when_filtering_noise(self):
        texts = ["page 20z check 48z steel 5002 steel", "page 20z check 48z steel 5002 steel"]
        vectorizer = build_vectorizer(filter_noise=True)

        vectorizer.fit(texts)

        self.assertNotIn("20z", vectorizer.vocabulary_)
        self.assertNotIn("48z", vectorizer.vocabulary_)
        self.assertIn("steel", vectorizer.vocabulary_)
        self.assertIn("5002", vectorizer.vocabulary_)

    def test_should_keep_mixed_tokens_by_default(self):
        texts = ["page 20z check 48z steel", "page 20z check 48z steel"]
        vectorizer = build_vectorizer()

        vectorizer.fit(texts)

        self.assertIn("20z", vectorizer.vocabulary_)
