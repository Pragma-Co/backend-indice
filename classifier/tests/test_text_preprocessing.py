from django.test import SimpleTestCase

from classifier import text_preprocessing
from classifier.text_preprocessing import preprocess_for_llm


class PreprocessForLlmTests(SimpleTestCase):
    def test_should_lowercase_drop_urls_punctuation_and_stopwords_and_lemmatize(self):
        text = "The Fuselage frames, ribs & https://x.io/a are riveted to www.site.com skins."

        result = preprocess_for_llm(text)

        self.assertEqual(result, "fuselage frame rib riveted skin")

    def test_should_return_empty_string_for_empty_text(self):
        result = preprocess_for_llm("")

        self.assertEqual(result, "")

    def test_should_check_nltk_resources_only_once_across_calls(self):
        text_preprocessing._ensure_nltk_resources.cache_clear()

        preprocess_for_llm("first document")
        preprocess_for_llm("second document")

        self.assertEqual(text_preprocessing._ensure_nltk_resources.cache_info().misses, 1)
