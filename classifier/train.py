import argparse
import sys
from pathlib import Path

import joblib

from classifier.catalog import (
    DEFAULT_CATALOG_PATH,
    CatalogError,
    load_catalog,
    load_criteria_version,
)
from classifier.dataset import DatasetValidationError, load_dataset
from classifier.evaluation import format_evaluation
from classifier.neural_training import TrainingConfig
from classifier.persistence import DEFAULT_OUTPUT_DIR, VECTORIZER_FILENAME, save_model
from classifier.splitting import SplitError
from classifier.training_run import StoredFeatures, run_training
from classifier.vector_store import VectorStoreError, get_vector_store, vectorizer_version


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m classifier.train")
    parser.add_argument("--csv", required=True, help="Training dataset (UTF-8 CSV).")
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="JSON file with the valid labels per field and the criteria version.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory that receives the trained model and metadata.json.",
    )
    parser.add_argument(
        "--vectors-from-mongo",
        action="store_true",
        help="Read the TF-IDF vectors stored by classifier.vectorize instead of fitting them.",
    )
    add_network_options(parser)
    return parser


def load_stored_features(dataset, output_dir) -> StoredFeatures:
    path = Path(output_dir) / VECTORIZER_FILENAME
    if not path.is_file():
        raise VectorStoreError(f"{path} not found; run python -m classifier.vectorize first")
    vectorizer = joblib.load(path)
    features = get_vector_store().load(dataset.texts, vectorizer_version(vectorizer))
    return StoredFeatures(vectorizer=vectorizer, features=features)


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)

    try:
        catalog = load_catalog(arguments.catalog)
        criteria_version = load_criteria_version(arguments.catalog)
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
        stored = None
        if arguments.vectors_from_mongo:
            stored = load_stored_features(dataset, arguments.output_dir)
            print(f"{stored.features.shape[0]} vectors read from MongoDB")
        training = run_training(
            dataset, config_from(arguments), stored=stored, filter_noise=arguments.filter_noise
        )
    except (SplitError, VectorStoreError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for evaluation in training.evaluations.values():
        print()
        print(format_evaluation(evaluation, len(training.split.train)))

    directory = save_model(
        training.trained,
        training.vectorizer,
        training.evaluations,
        arguments.csv,
        catalog,
        criteria_version,
        len(dataset.texts),
        arguments.output_dir,
    )
    print(f"\nmodel saved to {directory}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
