import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

from classifier.catalog import DEFAULT_CATALOG_PATH, load_area_groups

DEFAULT_DATASET = "training_export/quicksearch/dataset.csv"
DEFAULT_METADATA = "training_export/quicksearch/metadata.jsonl"
DEFAULT_REVIEW = "training_export/quicksearch/area_review.csv"
DEFAULT_AGREEMENT = "training_export/quicksearch/area_agreement.json"
SAMPLE_SIZE = 60
SAMPLE_SEED = 42
EXCERPT_CHARS = 1500
REVIEW_COLUMNS = ("document_id", "title", "excerpt", "human_stage")
CSV_FIELD_SIZE_LIMIT = 2**31 - 1


def read_csv(path) -> list[dict]:
    csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_titles(metadata_path) -> dict[str, str]:
    titles = {}
    path = Path(metadata_path)
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    titles[record["document_id"]] = record["title"]
    return titles


def draw_sample(rows: list[dict], size: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED) -> list[dict]:
    return random.Random(seed).sample(rows, min(size, len(rows)))


def build_review_rows(sample: list[dict], titles: dict[str, str]) -> list[dict]:
    return [
        {
            "document_id": row["document_id"],
            "title": titles.get(row["document_id"], ""),
            "excerpt": row["text"][:EXCERPT_CHARS],
            "human_stage": "",
        }
        for row in sample
    ]


def compute_agreement(
    dataset_rows: list[dict], review_rows: list[dict], groups: dict[str, str]
) -> dict:
    ai_by_document = {
        row["document_id"]: row.get("area_stage") or row["area"] for row in dataset_rows
    }
    compared_by_stage, agreed_by_stage = Counter(), Counter()
    compared_by_class, agreed_by_class = Counter(), Counter()
    ignored = 0
    for review in review_rows:
        human = review["human_stage"].strip()
        ai = ai_by_document.get(review["document_id"])
        if human not in groups or ai not in groups:
            ignored += 1
            continue
        compared_by_stage[ai] += 1
        agreed_by_stage[ai] += human == ai
        compared_by_class[groups[ai]] += 1
        agreed_by_class[groups[ai]] += groups[human] == groups[ai]
    total = sum(compared_by_stage.values())
    return {
        "rate": sum(agreed_by_class.values()) / total if total else 0.0,
        "rate_fine": sum(agreed_by_stage.values()) / total if total else 0.0,
        "sample_size": total,
        "ignored_rows": ignored,
        "by_area_class": {
            label: {"compared": compared_by_class[label], "agreed": agreed_by_class[label]}
            for label in sorted(compared_by_class)
        },
        "by_ai_label": {
            label: {"compared": compared_by_stage[label], "agreed": agreed_by_stage[label]}
            for label in sorted(compared_by_stage)
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.dataset.area_review")
    commands = parser.add_subparsers(dest="command", required=True)

    sample = commands.add_parser("sample", help="Write the blind review sheet.")
    sample.add_argument("--dataset", default=DEFAULT_DATASET)
    sample.add_argument("--metadata", default=DEFAULT_METADATA)
    sample.add_argument("--output", default=DEFAULT_REVIEW)
    sample.add_argument("--size", type=int, default=SAMPLE_SIZE)
    sample.add_argument("--seed", type=int, default=SAMPLE_SEED)
    sample.add_argument(
        "--exclude-from",
        default=None,
        help="Review sheet whose documents must not be drawn again.",
    )

    agreement = commands.add_parser("agreement", help="Compare the filled sheet with the AI.")
    agreement.add_argument("--dataset", default=DEFAULT_DATASET)
    agreement.add_argument("--review", default=DEFAULT_REVIEW)
    agreement.add_argument("--catalog", default=str(DEFAULT_CATALOG_PATH))
    agreement.add_argument("--output", default=DEFAULT_AGREEMENT)
    agreement.add_argument(
        "--reviewer",
        default="human",
        help="Who filled the sheet (human, or the name of a reference model).",
    )
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)

    if arguments.command == "sample":
        candidates = read_csv(arguments.dataset)
        if arguments.exclude_from:
            excluded = {row["document_id"] for row in read_csv(arguments.exclude_from)}
            candidates = [row for row in candidates if row["document_id"] not in excluded]
        sample = draw_sample(candidates, arguments.size, arguments.seed)
        review_rows = build_review_rows(sample, load_titles(arguments.metadata))
        with Path(arguments.output).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
            writer.writeheader()
            writer.writerows(review_rows)
        print(f"{len(review_rows)} documents to review written to {arguments.output}")
        return 0

    result = compute_agreement(
        read_csv(arguments.dataset),
        read_csv(arguments.review),
        load_area_groups(arguments.catalog),
    )
    result["reviewer"] = arguments.reviewer
    Path(arguments.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"agreement with {arguments.reviewer}: {result['rate']:.1%} on the area classes, "
        f"{result['rate_fine']:.1%} on the six stages, over {result['sample_size']} documents"
    )
    if result["ignored_rows"]:
        print(f"{result['ignored_rows']} rows ignored (no valid stage on one side)", file=sys.stderr)
    print("by area class (AI label):")
    for label, counts in result["by_area_class"].items():
        print(f"  {label}: {counts['agreed']}/{counts['compared']}")
    print("by stage (AI label):")
    for label, counts in result["by_ai_label"].items():
        print(f"  {label}: {counts['agreed']}/{counts['compared']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
