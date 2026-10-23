import argparse
import sys
from pathlib import Path

from classifier.persistence import DEFAULT_OUTPUT_DIR, ArtifactsError
from classifier.prediction import Classifier


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from scripts.dataset.build_csv import extract_text

        return extract_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def format_predictions(predictions: dict) -> str:
    width = max(len(name) for name in predictions)
    return "\n".join(
        f"{name:<{width}}  {prediction.label:<16} {prediction.confidence:.1%}"
        for name, prediction in predictions.items()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m classifier.predict")
    parser.add_argument("--file", required=True, help="PDF or UTF-8 text file to classify.")
    parser.add_argument("--model-dir", default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    path = Path(arguments.file)
    if not path.is_file():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 1
    try:
        text = read_text(path)
        predictions = Classifier(arguments.model_dir).predict(text)
    except (ArtifactsError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{path.name}: {len(text)} characters")
    print(format_predictions(predictions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
