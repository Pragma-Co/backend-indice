import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from PyPDF2 import PdfReader

DEFAULT_METADATA = "training_export/quicksearch/metadata.jsonl"
DEFAULT_PDF_DIR = "training_export/quicksearch/pdfs"
DEFAULT_CSV = "training_export/quicksearch/dataset.csv"
DEFAULT_CATALOG = "training_export/quicksearch/catalog.json"
PDF_FILENAME = "document.pdf"
MIN_TEXT_CHARS = 2000
MAX_TEXT_CHARS = 50000
MIN_CLASS_DOCS = 15
OTHER = "OTHER"
FIELDS = ("discipline", "document_type", "area")
CSV_COLUMNS = ("texto", "disciplina", "tipo", "area", "ident_number", "document_id")

DOCUMENT_TYPES = {
    "Detail Specification": "DETAIL_SPEC",
    "Federal Specification": "FEDERAL_SPEC",
    "Commercial Item Description (CID)": "CID",
    "Performance Specification": "PERFORMANCE_SPEC",
    "Defense Handbook": "HANDBOOK",
}
MILITARY_STANDARD_PREFIX = "Military Standard"
AREA_KEYWORDS = (
    ("DLA", "DLA"),
    ("GSA", "General Services"),
    ("NAVY", "Naval"),
    ("NAVY", "Navy"),
    ("AIR_FORCE", "Air Force"),
    ("ARMY", "Army"),
    ("ARMY", "Ground Vehicle"),
    ("ARMY", "Combat Capabilities"),
)


def document_type_label(doc_category: str) -> str:
    if doc_category.startswith(MILITARY_STANDARD_PREFIX):
        return "MILITARY_STD"
    return DOCUMENT_TYPES.get(doc_category, OTHER)


def area_label(preparing_activity: str) -> str:
    for label, keyword in AREA_KEYWORDS:
        if keyword in preparing_activity:
            return label
    return OTHER


def extract_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for index in range(len(reader.pages)):
        try:
            pages.append(reader.pages[index].extract_text() or "")
        except Exception:
            continue
        if sum(len(page) for page in pages) >= MAX_TEXT_CHARS:
            break
    return "\n".join(pages)[:MAX_TEXT_CHARS]


def merge_small_classes(rows: list[dict], min_docs: int) -> None:
    for field in FIELDS:
        counts = Counter(row[field] for row in rows)
        for row in rows:
            if counts[row[field]] < min_docs:
                row[field] = OTHER


def drop_lonely_other(rows: list[dict]) -> list[dict]:
    kept = rows
    for field in FIELDS:
        if sum(1 for row in kept if row[field] == OTHER) == 1:
            kept = [row for row in kept if row[field] != OTHER]
    return kept


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scripts/dataset/build_csv.py")
    parser.add_argument("--metadata", default=DEFAULT_METADATA)
    parser.add_argument("--pdf-dir", default=DEFAULT_PDF_DIR)
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--min-class-docs", type=int, default=MIN_CLASS_DOCS)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    with Path(arguments.metadata).open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]

    rows = []
    skipped = Counter()
    for record in records:
        if not record["selected_part"]:
            skipped["no public part"] += 1
            continue
        path = Path(arguments.pdf_dir) / str(record["ident_number"]) / PDF_FILENAME
        if not path.is_file():
            skipped["not downloaded"] += 1
            continue
        try:
            text = extract_text(path)
        except Exception:
            skipped["unreadable pdf"] += 1
            continue
        if len(text.strip()) < MIN_TEXT_CHARS:
            skipped["too little text"] += 1
            continue
        rows.append(
            {
                "texto": text,
                "discipline": f"FSC{record['fsc'][:2]}",
                "document_type": document_type_label(record["doc_category"]),
                "area": area_label(record["preparing_activity"]),
                "ident_number": record["ident_number"],
                "document_id": record["document_id"],
            }
        )

    merge_small_classes(rows, arguments.min_class_docs)
    rows = drop_lonely_other(rows)

    with Path(arguments.csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row["texto"],
                    row["discipline"],
                    row["document_type"],
                    row["area"],
                    row["ident_number"],
                    row["document_id"],
                ]
            )

    catalog = {field: sorted({row[field] for row in rows}) for field in FIELDS}
    Path(arguments.catalog).write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"{len(rows)} documents written to {arguments.csv}")
    print(f"skipped: {dict(skipped)}")
    for field in FIELDS:
        print(f"{field}: {dict(Counter(row[field] for row in rows).most_common())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
