from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from core.services.document_text_service import (
    CONTENT_EXCERPT_MAX_CHARS,
    TITLE_EXCERPT_MAX_CHARS,
    build_content_excerpt,
    build_title_excerpt,
    extract_raw_text,
    extract_text_for_ai,
    ingest_text,
    is_table_of_contents,
)

TABLE_OF_CONTENTS_PAGE = (
    "1 Scope ........................ 3\n"
    "2 Requirements ................. 5\n"
    "3 Verification . . . . . . . . . 9\n"
)


def pages(count: int) -> list[str]:
    return [f"page {number} body" for number in range(count)]


class ExtractTextForAiTests(SimpleTestCase):
    def test_given_unsupported_extension_when_extracted_then_returns_empty_string(self):
        result = extract_text_for_ai(Path("document.png"), "png")

        self.assertEqual(result, "")

    @mock.patch("core.services.document_text_service.extract_text_segments")
    def test_given_raw_extraction_fails_when_extracted_then_returns_empty_string(
        self, mock_extract_text_segments
    ):
        mock_extract_text_segments.side_effect = Exception("corrupted file")

        result = extract_text_for_ai(Path("document.pdf"), "pdf")

        self.assertEqual(result, "")

    @mock.patch("core.services.document_text_service.preprocess_for_llm")
    @mock.patch("core.services.document_text_service.extract_text_segments")
    def test_given_preprocessing_fails_when_extracted_then_returns_empty_string(
        self, mock_extract_text_segments, mock_preprocess_for_llm
    ):
        mock_extract_text_segments.return_value = ["conteudo"]
        mock_preprocess_for_llm.side_effect = Exception("nltk data missing")

        result = extract_text_for_ai(Path("document.docx"), "docx")

        self.assertEqual(result, "")


class ExtractRawTextTests(SimpleTestCase):
    @mock.patch("core.services.document_text_service.extract_text_segments")
    def test_given_segments_when_extracted_then_joins_them_with_line_breaks(
        self, mock_extract_text_segments
    ):
        mock_extract_text_segments.return_value = ["cover", "body"]

        result = extract_raw_text(Path("document.pdf"), "pdf")

        self.assertEqual(result, "cover\nbody")


class TableOfContentsTests(SimpleTestCase):
    def test_given_heading_when_checked_then_detects_table_of_contents(self):
        for heading in ("Sumário", "ÍNDICE", "Table of Contents", "CONTENTS"):
            with self.subTest(heading=heading):
                page = f"MIL-STD-883\n  {heading}  \n1 Scope 3"

                result = is_table_of_contents(page)

                self.assertTrue(result)

    def test_given_dot_leader_entries_when_checked_then_detects_table_of_contents(self):
        result = is_table_of_contents(TABLE_OF_CONTENTS_PAGE)

        self.assertTrue(result)

    def test_given_regular_page_when_checked_then_is_not_table_of_contents(self):
        page = "This standard covers the contents of the test method.\nSee section 4 ... 12"

        result = is_table_of_contents(page)

        self.assertFalse(result)


class TitleExcerptTests(SimpleTestCase):
    def test_given_pdf_when_built_then_uses_only_the_first_page_with_text(self):
        segments = ["  \n", "Test Method\n  Standard", "body of the document"]

        result = build_title_excerpt(segments, "pdf")

        self.assertEqual(result, "Test Method Standard")

    def test_given_docx_when_built_then_uses_the_leading_paragraphs(self):
        segments = ["Test Method", "", "Standard"]

        result = build_title_excerpt(segments, "docx")

        self.assertEqual(result, "Test Method Standard")

    def test_given_long_first_page_when_built_then_truncates_it(self):
        segments = ["a" * (TITLE_EXCERPT_MAX_CHARS + 100)]

        result = build_title_excerpt(segments, "pdf")

        self.assertEqual(len(result), TITLE_EXCERPT_MAX_CHARS)

    def test_given_no_text_when_built_then_returns_empty_string(self):
        result = build_title_excerpt(["", "  "], "pdf")

        self.assertEqual(result, "")


class ContentExcerptTests(SimpleTestCase):
    def test_given_long_document_when_built_then_starts_at_fifteen_percent(self):
        segments = pages(20)

        result = build_content_excerpt(segments)

        self.assertTrue(result.startswith("page 3 body"))

    def test_given_table_of_contents_at_start_when_built_then_skips_it(self):
        segments = pages(20)
        segments[3] = TABLE_OF_CONTENTS_PAGE
        segments[4] = "Table of Contents\ncontinued"

        result = build_content_excerpt(segments)

        self.assertTrue(result.startswith("page 5 body"))

    def test_given_short_document_when_built_then_starts_after_the_first_page(self):
        segments = pages(3)

        result = build_content_excerpt(segments)

        self.assertEqual(result, "page 1 body page 2 body")

    def test_given_single_page_when_built_then_returns_empty_string(self):
        result = build_content_excerpt(pages(1))

        self.assertEqual(result, "")

    def test_given_only_table_of_contents_left_when_built_then_keeps_the_last_page(self):
        segments = ["cover", TABLE_OF_CONTENTS_PAGE]

        result = build_content_excerpt(segments)

        self.assertTrue(result.startswith("1 Scope"))

    def test_given_long_content_when_built_then_truncates_it(self):
        segments = ["cover", "b" * (CONTENT_EXCERPT_MAX_CHARS + 100)]

        result = build_content_excerpt(segments)

        self.assertEqual(len(result), CONTENT_EXCERPT_MAX_CHARS)


class IngestTextTests(SimpleTestCase):
    @mock.patch("core.services.document_text_service.preprocess_for_llm")
    @mock.patch("core.services.document_text_service.extract_text_segments")
    def test_given_pdf_when_ingested_then_returns_text_and_excerpts(
        self, mock_extract_text_segments, mock_preprocess_for_llm
    ):
        mock_extract_text_segments.return_value = ["Cover Title", "Body text"]
        mock_preprocess_for_llm.return_value = "cover title body text"

        result = ingest_text(Path("document.pdf"), "pdf")

        self.assertEqual(result["extraction"], "SUCCESS")
        self.assertEqual(result["text"], "cover title body text")
        self.assertEqual(result["title_excerpt"], "Cover Title")
        self.assertEqual(result["content_excerpt"], "Body text")

    def test_given_unsupported_extension_when_ingested_then_returns_empty_excerpts(self):
        result = ingest_text(Path("document.png"), "png")

        self.assertEqual(result["extraction"], "SKIPPED")
        self.assertEqual(result["title_excerpt"], "")
        self.assertEqual(result["content_excerpt"], "")
