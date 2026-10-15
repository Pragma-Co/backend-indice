import logging
import re
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.contrib.postgres.search import SearchVector

from core.models import Document, DocumentContent, Revision
from core.models.search import SEARCH_CONFIG, THEMATIC_TAG_MAX_LENGTH
from core.services.document_text_service import (
    AI_TEXT_EXTENSIONS,
    extract_raw_text,
    normalize_for_search,
    search_stopwords,
)

logger = logging.getLogger(__name__)

MAX_INDEXED_CHARS = 200_000
THEMATIC_TAG_LIMIT = 8
THEMATIC_TAG_MIN_LENGTH = 4
THEMATIC_TAG_MIN_OCCURRENCES = 2
WORD_PATTERN = re.compile(r"[^\W\d_]+")


def generate_thematic_tags(content: str) -> list[str]:
    stop_words = search_stopwords()
    words = [
        word
        for word in WORD_PATTERN.findall(content.lower())
        if len(word) >= THEMATIC_TAG_MIN_LENGTH and word not in stop_words
    ]
    return [
        word[:THEMATIC_TAG_MAX_LENGTH]
        for word, occurrences in Counter(words).most_common(THEMATIC_TAG_LIMIT)
        if occurrences >= THEMATIC_TAG_MIN_OCCURRENCES
    ]


def save_document_content(
    document: Document, revision: Revision | None, content: str
) -> DocumentContent:
    content = normalize_for_search(content)[:MAX_INDEXED_CHARS]
    indexed, _created = DocumentContent.objects.update_or_create(
        document=document,
        defaults={
            "revision": revision,
            "content": content,
            "thematic_tags": generate_thematic_tags(content),
        },
    )
    DocumentContent.objects.filter(pk=indexed.pk).update(
        search_vector=SearchVector("content", weight="C", config=SEARCH_CONFIG)
    )
    return indexed


def _read_file_text(file) -> str:
    if file.extension not in AI_TEXT_EXTENSIONS:
        return ""
    path = Path(settings.DOCUMENT_STORAGE_DIR) / file.storage_path
    try:
        return extract_raw_text(path, file.extension)
    except Exception:
        logger.exception("Failed to extract text from file %s for search indexing", file.pk)
        return ""


def index_document(document: Document) -> DocumentContent:
    revision = document.revisions.order_by("-version").first()
    files = list(revision.files.order_by("id")) if revision is not None else []
    content = " ".join(_read_file_text(file) for file in files)
    return save_document_content(document, revision, content)


def index_document_safely(document: Document) -> None:
    try:
        index_document(document)
    except Exception:
        logger.exception("Failed to index document %s for search", document.pk)
