import csv
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db.models import OuterRef, Subquery

from core.models import File, Revision

CSV_FILENAME = "documents.csv"
FILES_DIRNAME = "files"
AREA_SEPARATOR = ";"
DEFAULT_EXTENSIONS = ("pdf", "docx")
CSV_COLUMNS = (
    "file",
    "sha256",
    "document_code",
    "title",
    "description",
    "project",
    "discipline",
    "areas",
    "document_type",
    "original_name",
    "revision_version",
)


@dataclass
class TrainingExportResult:
    exported: int = 0
    missing: list[str] = field(default_factory=list)


def export_training_data(output_dir, extensions=DEFAULT_EXTENSIONS):
    output_dir = Path(output_dir)
    files_dir = output_dir / FILES_DIRNAME
    files_dir.mkdir(parents=True, exist_ok=True)

    result = TrainingExportResult()
    rows = []
    for file_obj in _latest_revision_files(extensions):
        source = Path(settings.DOCUMENT_STORAGE_DIR) / file_obj.storage_path
        if not source.is_file():
            result.missing.append(file_obj.storage_path)
            continue

        relative_path = f"{FILES_DIRNAME}/{file_obj.sha256}.{file_obj.extension}"
        destination = output_dir / relative_path
        if not destination.exists():
            shutil.copyfile(source, destination)

        rows.append(_build_row(file_obj, relative_path))
        result.exported += 1

    with (output_dir / CSV_FILENAME).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return result


def _latest_revision_files(extensions):
    latest_version = (
        Revision.objects.filter(document=OuterRef("revision__document"))
        .order_by("-version")
        .values("version")[:1]
    )
    return (
        File.objects.filter(extension__in=extensions, revision__version=Subquery(latest_version))
        .select_related(
            "revision__document__project",
            "revision__document__discipline",
            "revision__document__document_type",
        )
        .prefetch_related("revision__document__areas")
        .order_by("revision__document__code", "id")
    )


def _build_row(file_obj, relative_path):
    revision = file_obj.revision
    document = revision.document
    areas = sorted(area.acronym for area in document.areas.all())
    return {
        "file": relative_path,
        "sha256": file_obj.sha256,
        "document_code": document.code,
        "title": document.title,
        "description": document.description,
        "project": document.project.code,
        "discipline": document.discipline.code,
        "areas": AREA_SEPARATOR.join(areas),
        "document_type": document.document_type.code,
        "original_name": file_obj.original_name,
        "revision_version": revision.version,
    }
