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
    codes = Document.objects.filter(code__startswith=f"{prefix}-").values_list("code", flat=True)
    highest = max((_sequence_of(code, prefix) for code in codes), default=0)
    return highest + 1
