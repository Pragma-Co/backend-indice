import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from classifier.catalog import FIELDS, load_catalog

CSV_COLUMNS = {
    "text": "texto",
    "discipline": "disciplina",
    "document_type": "tipo",
    "area": "area",
}
CSV_FIELD_SIZE_LIMIT = 2**31 - 1
MIN_EXAMPLES_PER_CLASS = 20
MIN_EXAMPLES_FOR_STRATIFIED_SPLIT = 2
MAX_ROWS_LISTED = 5


@dataclass
class DatasetReport:
    rows_read: int = 0
    class_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class Dataset:
    texts: list[str]
    labels: dict[str, list[str]]
    report: DatasetReport


class DatasetValidationError(Exception):
    def __init__(self, report: DatasetReport):
        self.report = report
        super().__init__("; ".join(report.errors))


def load_dataset(csv_path, catalog=None) -> Dataset:
    if catalog is None:
        catalog = load_catalog()
    report = DatasetReport()
    records = _read_records(Path(csv_path), report)

    texts = []
    labels = {name: [] for name in FIELDS}
    empty_text_rows = []
    invalid_labels = {name: {} for name in FIELDS}

    for row_number, record in enumerate(records, start=1):
        text = record[CSV_COLUMNS["text"]]
        if not text.strip():
            empty_text_rows.append(row_number)
            continue

        row_labels = {name: record[CSV_COLUMNS[name]].strip() for name in FIELDS}
        row_is_valid = True
        for name, label in row_labels.items():
            if label not in catalog[name]:
                invalid_labels[name].setdefault(label, []).append(row_number)
                row_is_valid = False

        if row_is_valid:
            texts.append(text)
            for name, label in row_labels.items():
                labels[name].append(label)

    report.rows_read = len(records)
    _report_empty_texts(report, empty_text_rows)
    _report_invalid_labels(report, invalid_labels)
    _report_class_counts(report, labels, catalog)

    if not texts and not report.errors:
        report.errors.append("The dataset has no usable rows")
    if report.errors:
        raise DatasetValidationError(report)
    return Dataset(texts=texts, labels=labels, report=report)


def _read_records(path: Path, report: DatasetReport) -> list[dict[str, str]]:
    csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            missing = [name for name in CSV_COLUMNS.values() if name not in columns]
            if missing:
                report.errors.append(f"Missing required columns: {', '.join(missing)}")
                raise DatasetValidationError(report)
            return [{key: value or "" for key, value in row.items()} for row in reader]
    except UnicodeDecodeError as exc:
        report.errors.append("The file is not valid UTF-8")
        raise DatasetValidationError(report) from exc


def _format_rows(rows: list[int]) -> str:
    listed = ", ".join(str(row) for row in rows[:MAX_ROWS_LISTED])
    remaining = len(rows) - MAX_ROWS_LISTED
    return f"{listed} and {remaining} more" if remaining > 0 else listed


def _report_empty_texts(report: DatasetReport, rows: list[int]) -> None:
    if rows:
        report.warnings.append(
            f"{len(rows)} rows with empty text were ignored (rows {_format_rows(rows)})"
        )


def _report_invalid_labels(report: DatasetReport, invalid_labels: dict) -> None:
    for name, by_label in invalid_labels.items():
        for label, rows in by_label.items():
            report.errors.append(
                f"{name}: label {label!r} is not in the catalog (rows {_format_rows(rows)})"
            )


def _report_class_counts(report: DatasetReport, labels: dict, catalog) -> None:
    for name in FIELDS:
        counts = Counter(labels[name])
        report.class_counts[name] = dict(sorted(counts.items()))

        if len(counts) < 2:
            report.errors.append(f"{name}: at least 2 classes with examples are required")
        for label in sorted(catalog[name]):
            count = counts.get(label, 0)
            if count == 0:
                report.warnings.append(f"{name}: class {label} has no examples")
            elif count < MIN_EXAMPLES_FOR_STRATIFIED_SPLIT:
                report.errors.append(
                    f"{name}: class {label} has {count} example, "
                    f"at least {MIN_EXAMPLES_FOR_STRATIFIED_SPLIT} are needed "
                    "for a stratified split"
                )
            elif count < MIN_EXAMPLES_PER_CLASS:
                report.warnings.append(
                    f"{name}: class {label} has only {count} examples "
                    f"(recommended: {MIN_EXAMPLES_PER_CLASS})"
                )
