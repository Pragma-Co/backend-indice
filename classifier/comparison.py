import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from classifier.baseline_training import predict_baseline, train_baseline
from classifier.catalog import (
    DEFAULT_CATALOG_PATH,
    FIELDS,
    CatalogError,
    load_catalog,
)
from classifier.dataset import Dataset, DatasetValidationError, load_dataset
from classifier.evaluation import FieldEvaluation, evaluate_fields, format_confusion_matrix
from classifier.neural_training import TrainingConfig
from classifier.splitting import Split, SplitError
from classifier.training_run import run_training

BASELINE_NAME = "A: logistic regression + TF-IDF"
NETWORK_NAME = "B: single network + TF-IDF"

SetupRunner = Callable[[Dataset, Split, dict[str, list[str]]], dict[str, FieldEvaluation]]


@dataclass
class AreaAgreement:
    rate: float
    sample_size: int
    reviewer: str = "human"
    label: str = ""
    rate_fine: float | None = None


@dataclass
class ComparisonReport:
    test_size: int
    setups: dict[str, dict[str, FieldEvaluation]]
    area_agreements: list[AreaAgreement] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_comparison(
    dataset: Dataset,
    config: TrainingConfig | None = None,
    extra_setups: dict[str, SetupRunner] | None = None,
    area_agreements: list[AreaAgreement] | None = None,
    filter_noise: bool = False,
) -> ComparisonReport:
    network_run = run_training(dataset, config, filter_noise=filter_noise)
    split = network_run.split
    classes = network_run.trained.classes

    test_texts = [dataset.texts[index] for index in split.test]
    expected = {
        name: [dataset.labels[name][index] for index in split.test] for name in FIELDS
    }
    baseline_predictions = predict_baseline(train_baseline(dataset, split), test_texts)

    setups = {
        BASELINE_NAME: evaluate_fields(expected, baseline_predictions, classes),
        NETWORK_NAME: network_run.evaluations,
    }
    for name, runner in (extra_setups or {}).items():
        setups[name] = runner(dataset, split, classes)
    return ComparisonReport(
        test_size=len(split.test), setups=setups, area_agreements=list(area_agreements or [])
    )


def format_f1_table(report: ComparisonReport) -> str:
    names = list(report.setups)
    field_width = max(len(name) for name in (*FIELDS, "mean"))
    header = " " * field_width + "".join(f"  {name:>{len(name)}}" for name in names)

    def row(label: str, values: list[float]) -> str:
        cells = "".join(f"  {value:>{len(name)}.3f}" for name, value in zip(names, values, strict=True))
        return f"{label:<{field_width}}{cells}"

    rows = [
        row(label, [report.setups[name][label].f1_macro for name in names]) for label in FIELDS
    ]
    means = [
        sum(report.setups[name][label].f1_macro for label in FIELDS) / len(FIELDS)
        for name in names
    ]
    return "\n".join([f"macro F1 on {report.test_size} test documents", header, *rows, row("mean", means)])


def format_report(report: ComparisonReport) -> str:
    sections = [format_f1_table(report)]
    for setup_name, evaluations in report.setups.items():
        for field_name in FIELDS:
            evaluation = evaluations[field_name]
            sections.append(
                "\n".join(
                    [
                        f"{setup_name} | {field_name} (accuracy {evaluation.accuracy:.3f}, "
                        f"macro F1 {evaluation.f1_macro:.3f})",
                        evaluation.report_text.rstrip(),
                        format_confusion_matrix(evaluation.labels, evaluation.confusion_matrix),
                    ]
                )
            )
    if report.area_agreements:
        sections.append("\n".join(format_area_agreement(a) for a in report.area_agreements))
    sections.extend(report.notes)
    return "\n\n".join(sections)


def format_area_agreement(agreement: AreaAgreement) -> str:
    label = f", {agreement.label}" if agreement.label else ""
    fine = f" ({agreement.rate_fine:.1%} on the six stages)" if agreement.rate_fine is not None else ""
    return (
        f"area: AI labeler agrees with the {agreement.reviewer} sample{label} on "
        f"{agreement.rate:.1%} of {agreement.sample_size} documents{fine}; "
        "the agreement on documents the criteria never saw is the ceiling for the area field"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m classifier.comparison")
    parser.add_argument("--csv", required=True, help="Training dataset (UTF-8 CSV).")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument(
        "--area-agreement",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="JSON written by scripts.dataset.area_review agreement; repeatable.",
    )
    add_network_options(parser)
    return parser


def add_network_options(parser: argparse.ArgumentParser) -> None:
    defaults = TrainingConfig()
    parser.add_argument("--hidden-size", type=int, default=defaults.hidden_size)
    parser.add_argument("--dropout", type=float, default=defaults.dropout)
    parser.add_argument("--weight-decay", type=float, default=defaults.weight_decay)
    parser.add_argument("--filter-noise", action="store_true")


def config_from(arguments) -> TrainingConfig:
    return TrainingConfig(
        hidden_size=arguments.hidden_size,
        dropout=arguments.dropout,
        weight_decay=arguments.weight_decay,
    )


def load_area_agreement(spec: str) -> AreaAgreement:
    label, separator, path = spec.rpartition("=")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AreaAgreement(
        rate=data["rate"],
        sample_size=data["sample_size"],
        reviewer=data.get("reviewer", "human"),
        label=label if separator else "",
        rate_fine=data.get("rate_fine"),
    )


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        dataset = load_dataset(arguments.csv, load_catalog(arguments.catalog))
        report = run_comparison(
            dataset,
            config_from(arguments),
            filter_noise=arguments.filter_noise,
            area_agreements=[load_area_agreement(spec) for spec in arguments.area_agreement],
        )
    except (CatalogError, DatasetValidationError) as exc:
        report_errors = getattr(exc, "report", None)
        for message in report_errors.errors if report_errors else [str(exc)]:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1
    except SplitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
