from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from core.services.document_text_service import extract_text_for_ai


class ExtractTextForAiTests(SimpleTestCase):
    def test_given_unsupported_extension_when_extracted_then_returns_empty_string(self):
        result = extract_text_for_ai(Path("document.png"), "png")

        self.assertEqual(result, "")

    @mock.patch("core.services.document_text_service.extract_raw_text")
    def test_given_raw_extraction_fails_when_extracted_then_returns_empty_string(
        self, mock_extract_raw_text
    ):
        mock_extract_raw_text.side_effect = Exception("corrupted file")

        result = extract_text_for_ai(Path("document.pdf"), "pdf")

        self.assertEqual(result, "")

    @mock.patch("core.services.document_text_service.preprocess_for_llm")
    @mock.patch("core.services.document_text_service.extract_raw_text")
    def test_given_preprocessing_fails_when_extracted_then_returns_empty_string(
        self, mock_extract_raw_text, mock_preprocess_for_llm
    ):
        mock_extract_raw_text.return_value = "conteudo"
        mock_preprocess_for_llm.side_effect = Exception("nltk data missing")

        result = extract_text_for_ai(Path("document.docx"), "docx")

        self.assertEqual(result, "")
