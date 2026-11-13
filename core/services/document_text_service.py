import logging
import re
import unicodedata
from pathlib import Path

from docx import Document as DocxDocument
from nltk.corpus import stopwords
from PyPDF2 import PdfReader

from classifier.text_preprocessing import ensure_nltk_resources, preprocess_for_llm

logger = logging.getLogger(__name__)

AI_TEXT_EXTENSIONS = {"pdf", "docx"}
MAX_CHARS_SENT_TO_MODEL = 20000
TITLE_EXCERPT_MAX_CHARS = 1500
CONTENT_EXCERPT_MAX_CHARS = 3500
CONTENT_START_FRACTION = 0.15
TABLE_OF_CONTENTS_MIN_ENTRIES = 3
TABLE_OF_CONTENTS_HEADING = re.compile(
    r"^\s*(?:sum[áa]rio|[íi]ndice|table\s+of\s+contents|contents)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TABLE_OF_CONTENTS_ENTRY = re.compile(r"(?:(?:\.\s?){3,}|…+)\s*\d+\s*$", re.MULTILINE)


def _extract_pdf_pages(path: Path) -> list[str]:
    with open(path, "rb") as stream:
        return [page.extract_text() or "" for page in PdfReader(stream).pages]


def _extract_docx_paragraphs(path: Path) -> list[str]:
    return [paragraph.text for paragraph in DocxDocument(path).paragraphs]


def extract_text_segments(path: Path, extension: str) -> list[str]:
    if extension == "pdf":
        return _extract_pdf_pages(path)
    if extension == "docx":
        return _extract_docx_paragraphs(path)
    return []


def extract_raw_text(path: Path, extension: str) -> str:
    return "\n".join(extract_text_segments(path, extension))


def _searchable_char(char: str) -> str:
    category = unicodedata.category(char)
    if category == "Cc":
        return " "
    return "" if category.startswith("C") else char


def normalize_for_search(text: str) -> str:
    text = "".join(_searchable_char(char) for char in unicodedata.normalize("NFC", text))
    return re.sub(r"\s+", " ", text).strip()


def search_stopwords() -> set[str]:
    ensure_nltk_resources()
    return set(stopwords.words("portuguese")) | set(stopwords.words("english"))


EXTRACTION_SUCCESS = "SUCCESS"
EXTRACTION_EMPTY = "EMPTY"
EXTRACTION_SKIPPED = "SKIPPED"
EXTRACTION_FAILURE = "FAILURE"


def is_table_of_contents(segment: str) -> bool:
    if TABLE_OF_CONTENTS_HEADING.search(segment):
        return True
    return len(TABLE_OF_CONTENTS_ENTRY.findall(segment)) >= TABLE_OF_CONTENTS_MIN_ENTRIES


def _content_start(segments: list[str]) -> int:
    last = len(segments) - 1
    start = min(max(1, int(len(segments) * CONTENT_START_FRACTION)), last)
    while start < last and is_table_of_contents(segments[start]):
        start += 1
    return start


def build_title_excerpt(segments: list[str], extension: str) -> str:
    readable = [text for text in map(normalize_for_search, segments) if text]
    if not readable:
        return ""
    source = readable[0] if extension == "pdf" else " ".join(readable)
    return source[:TITLE_EXCERPT_MAX_CHARS].strip()


def build_content_excerpt(segments: list[str]) -> str:
    if len(segments) < 2:
        return ""
    content = normalize_for_search(" ".join(segments[_content_start(segments) :]))
    return content[:CONTENT_EXCERPT_MAX_CHARS].strip()


def _ingestion(
    text: str,
    extraction: str,
    detail: str | None,
    title_excerpt: str = "",
    content_excerpt: str = "",
) -> dict:
    return {
        "text": text,
        "extraction": extraction,
        "detail": detail,
        "title_excerpt": title_excerpt,
        "content_excerpt": content_excerpt,
    }


def ingest_text(path: Path, extension: str) -> dict:
    if extension not in AI_TEXT_EXTENSIONS:
        return _ingestion("", EXTRACTION_SKIPPED, f"No text extraction for {extension} files.")
    try:
        segments = extract_text_segments(path, extension)
        text = preprocess_for_llm("\n".join(segments))[:MAX_CHARS_SENT_TO_MODEL]
    except Exception as exc:
        logger.exception("Failed to extract text from %s for AI suggestions", path.name)
        return _ingestion("", EXTRACTION_FAILURE, f"Text extraction failed: {type(exc).__name__}.")
    if not text:
        return _ingestion("", EXTRACTION_EMPTY, "No text found in the file.")
    return _ingestion(
        text,
        EXTRACTION_SUCCESS,
        None,
        title_excerpt=build_title_excerpt(segments, extension),
        content_excerpt=build_content_excerpt(segments),
    )


def extract_text_for_ai(path: Path, extension: str) -> str:
    return ingest_text(path, extension)["text"]
