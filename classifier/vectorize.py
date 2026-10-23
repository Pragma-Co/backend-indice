import argparse
import sys
from pathlib import Path

import joblib

from classifier.catalog import DEFAULT_CATALOG_PATH, CatalogError, load_catalog
from classifier.dataset import DatasetValidationError, load_dataset
from classifier.persistence import DEFAULT_OUTPUT_DIR, VECTORIZER_FILENAME
from classifier.splitting import RANDOM_STATE, SplitError, split_dataset
from classifier.tfidf_input import MAX_FEATURES, build_vectorizer
from classifier.vector_store import get_vector_store, vectorizer_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m classifier.vectorize")
    parser.add_argument("--csv", required=True, help="Training dataset (UTF-8 CSV).")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--max-features", type=int, default=MAX_FEATURES)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    parser.add_argument("--filter-noise", action="store_true")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory that receives vectorizer.joblib (the same one classifier.train uses).",
    )
    return parser


def fit_and_store(dataset, store, max_features: int, random_state: int, filter_noise=False):
    split = split_dataset(dataset, random_state)
    vectorizer = build_vectorizer(max_features, filter_noise)
    vectorizer.fit([dataset.texts[index] for index in split.train])
    features = vectorizer.transform(dataset.texts)
    version = vectorizer_version(vectorizer)
    stored = store.save_all(dataset.texts, features, version)
    return vectorizer, version, stored


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        dataset = load_dataset(arguments.csv, load_catalog(arguments.catalog))
        vectorizer, version, stored = fit_and_store(
            dataset,
            get_vector_store(),
            arguments.max_features,
            arguments.random_state,
            arguments.filter_noise,
        )
    except (CatalogError, DatasetValidationError, SplitError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_dir = Path(arguments.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, output_dir / VECTORIZER_FILENAME)
    print(
        f"{stored} vectors stored with {len(vectorizer.vocabulary_)} features, "
        f"vectorizer version {version[:12]}, saved to {output_dir / VECTORIZER_FILENAME}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
