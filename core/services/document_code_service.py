"""Deterministic generation of the document identifier code.

Pattern: ``PROJECT-DISCIPLINE-TYPE-NNNN`` (e.g. ``AK-2100-EST-DWG-0001``), the
same convention used by the demo seed. The three prefixes come straight from
the catalog codes; the trailing sequence numbers the documents that share the
same prefix, which is what keeps the code unique. The revision is *not* part
of the code: it lives in the ``revision`` table (version 1 is shown as
``REV01``), so a document keeps its code across revisions.
"""

from core.models import Discipline, Document, DocumentType, Project

SEQUENCE_WIDTH = 4


def build_code_prefix(project: Project, discipline: Discipline, document_type: DocumentType) -> str:
    return f"{project.code}-{discipline.code}-{document_type.code}".upper()


def build_document_code(prefix: str, sequence: int) -> str:
    return f"{prefix}-{sequence:0{SEQUENCE_WIDTH}d}"


def _sequence_of(code: str, prefix: str) -> int:
    suffix = code[len(prefix) + 1 :]
    return int(suffix) if suffix.isdigit() else 0


def next_sequence(prefix: str) -> int:
    """Return the next free sequence for the prefix (1 when none exists yet).

    The value is a best effort under concurrency: two requests may read the
    same number at once. The UNIQUE constraint on ``document.code`` is the
    real guard, and the creation service retries with a fresh sequence when
    it trips.
    """
    codes = Document.objects.filter(code__startswith=f"{prefix}-").values_list("code", flat=True)
    highest = max((_sequence_of(code, prefix) for code in codes), default=0)
    return highest + 1
