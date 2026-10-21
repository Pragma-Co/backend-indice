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


def _extract_from_pdf(path: Path) -> str:
    text = ""
    with open(path, "rb") as stream:
        reader = PdfReader(stream)
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
    return text


def _extract_from_docx(path: Path) -> str:
    document = DocxDocument(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_raw_text(path: Path, extension: str) -> str:
    if extension == "pdf":
        return _extract_from_pdf(path)
    if extension == "docx":
        return _extract_from_docx(path)
    return ""


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


def _ingestion(text: str, extraction: str, detail: str | None) -> dict:
    return {"text": text, "extraction": extraction, "detail": detail}


def ingest_text(path: Path, extension: str) -> dict:
    if extension not in AI_TEXT_EXTENSIONS:
        return _ingestion("", EXTRACTION_SKIPPED, f"No text extraction for {extension} files.")
    try:
        raw_text = extract_raw_text(path, extension)
        text = preprocess_for_llm(raw_text)[:MAX_CHARS_SENT_TO_MODEL]
    except Exception as exc:
        logger.exception("Failed to extract text from %s for AI suggestions", path.name)
        return _ingestion("", EXTRACTION_FAILURE, f"Text extraction failed: {type(exc).__name__}.")
    if not text:
        return _ingestion("", EXTRACTION_EMPTY, "No text found in the file.")
    return _ingestion(text, EXTRACTION_SUCCESS, None)


def extract_text_for_ai(path: Path, extension: str) -> str:
    return ingest_text(path, extension)["text"]
