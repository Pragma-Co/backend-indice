import argparse
import csv
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from PyPDF2 import PdfReader

from scripts.dataset.document_group import group_key
from scripts.dataset.label_maps import UnmappedLabelError, discipline_for, document_type_for

DEFAULT_METADATA = "training_export/quicksearch/metadata.jsonl"
DEFAULT_PDF_DIR = "training_export/quicksearch/pdfs"
DEFAULT_CSV = "training_export/quicksearch/dataset_unlabeled.csv"
PDF_FILENAME = "document.pdf"
MIN_TEXT_CHARS = 2000
MAX_TEXT_CHARS = 50000
CSV_COLUMNS = (
    "text",
    "title",
    "discipline",
    "document_type",
    "area",
    "group",
    "document_id",
    "ident_number",
)


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


def build_rows(
    records: list[dict], text_for: Callable[[dict], str | None], skipped: Counter
) -> list[dict]:
    rows = []
    seen_documents = set()
    for record in sorted(records, key=lambda item: item["ident_number"]):
        if not record["selected_part"]:
            skipped["no public part"] += 1
            continue
        if record["document_id"] in seen_documents:
            skipped["duplicate document"] += 1
            continue
        try:
            document_type = document_type_for(record["doc_category"])
            discipline = discipline_for(record["fsc"])
        except UnmappedLabelError as exc:
            skipped[f"unmapped: {exc}"] += 1
            continue
        text = text_for(record)
        if text is None:
            skipped["pdf not downloaded or unreadable"] += 1
            continue
        if len(text.strip()) < MIN_TEXT_CHARS:
            skipped["too little text"] += 1
            continue

        seen_documents.add(record["document_id"])
        rows.append(
            {
                "text": text,
                "title": record.get("title", ""),
                "discipline": discipline,
                "document_type": document_type,
                "area": "",
                "group": group_key(record["document_id"]),
                "document_id": record["document_id"],
                "ident_number": record["ident_number"],
            }
        )
    return rows


def pdf_text_reader(pdf_dir: Path) -> Callable[[dict], str | None]:
    def read(record: dict) -> str | None:
        path = pdf_dir / str(record["ident_number"]) / PDF_FILENAME
        if not path.is_file():
            return None
        try:
            return extract_text(path)
        except Exception:
            return None

    return read


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.dataset.build_csv")
    parser.add_argument("--metadata", default=DEFAULT_METADATA)
    parser.add_argument("--pdf-dir", default=DEFAULT_PDF_DIR)
    parser.add_argument("--csv", default=DEFAULT_CSV)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    with Path(arguments.metadata).open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]

    skipped = Counter()
    rows = build_rows(records, pdf_text_reader(Path(arguments.pdf_dir)), skipped)

    with Path(arguments.csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} documents written to {arguments.csv}")
    print(f"skipped: {dict(skipped)}")
    for name in ("discipline", "document_type"):
        print(f"{name}: {dict(Counter(row[name] for row in rows).most_common())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
