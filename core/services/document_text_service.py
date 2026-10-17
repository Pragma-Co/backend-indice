import logging
from pathlib import Path

from docx import Document as DocxDocument
from PyPDF2 import PdfReader

from classifier.text_preprocessing import preprocess_for_llm

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


def extract_text_for_ai(path: Path, extension: str) -> str:
    if extension not in AI_TEXT_EXTENSIONS:
        return ""
    try:
        raw_text = extract_raw_text(path, extension)
        return preprocess_for_llm(raw_text)[:MAX_CHARS_SENT_TO_MODEL]
    except Exception:
        logger.exception("Failed to extract text from %s for AI suggestions", path.name)
        return ""
