import logging
import re
from pathlib import Path

import nltk
from docx import Document as DocxDocument
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

AI_TEXT_EXTENSIONS = {"pdf", "docx"}
MAX_CHARS_SENT_TO_MODEL = 20000

NLTK_RESOURCES = {
    "stopwords": "corpora/stopwords",
    "punkt": "tokenizers/punkt",
    "punkt_tab": "tokenizers/punkt_tab",
    "wordnet": "corpora/wordnet",
    "omw-1.4": "corpora/omw-1.4",
}


def _ensure_nltk_resources() -> None:
    for package, resource_path in NLTK_RESOURCES.items():
        try:
            nltk.data.find(resource_path)
        except LookupError:
            nltk.download(package, quiet=True)


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


def clean_and_normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\n", " ").replace("\f", " ")
    return text.lower().strip()


def preprocess_for_llm(text: str) -> str:
    _ensure_nltk_resources()

    text = clean_and_normalize_text(text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"[\W_]+", " ", text)

    words = word_tokenize(text)
    stop_words = set(stopwords.words("english"))
    words = [word for word in words if word not in stop_words]

    lemmatizer = WordNetLemmatizer()
    words = [lemmatizer.lemmatize(word) for word in words]

    return " ".join(words)


def extract_text_for_ai(path: Path, extension: str) -> str:
    if extension not in AI_TEXT_EXTENSIONS:
        return ""
    try:
        raw_text = extract_raw_text(path, extension)
        return preprocess_for_llm(raw_text)[:MAX_CHARS_SENT_TO_MODEL]
    except Exception:
        logger.exception("Failed to extract text from %s for AI suggestions", path.name)
        return ""
