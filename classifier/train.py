import argparse
import sys

from classifier.catalog import DEFAULT_CATALOG_PATH, CatalogError, load_catalog
from classifier.dataset import DatasetValidationError, load_dataset
from classifier.evaluation import evaluate_all, format_evaluation
from classifier.training import TrainingError, train_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m classifier.train")
    parser.add_argument("--csv", required=True, help="Training dataset (UTF-8 CSV).")
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="JSON file with the valid labels per field.",
    )
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)

    try:
        catalog = load_catalog(arguments.catalog)
        dataset = load_dataset(arguments.csv, catalog)
    except (CatalogError, DatasetValidationError) as exc:
        report = getattr(exc, "report", None)
        for message in report.errors if report else [str(exc)]:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    for message in dataset.report.warnings:
        print(f"WARNING: {message}", file=sys.stderr)
    print(f"{len(dataset.texts)} usable documents out of {dataset.report.rows_read} rows")

    try:
        trained = train_all(dataset)
    except TrainingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for name, evaluation in evaluate_all(trained).items():
        print()
        print(format_evaluation(evaluation, trained[name].train_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
