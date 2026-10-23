import argparse
import json
import sys
from pathlib import Path

from scripts.dataset.quicksearch import PDF_SIGNATURE, REQUEST_DELAY_SECONDS, QuickSearchClient

DEFAULT_METADATA = "training_export/quicksearch/metadata.jsonl"
DEFAULT_OUTPUT_DIR = "training_export/quicksearch/pdfs"
PDF_FILENAME = "document.pdf"
PROGRESS_EVERY = 10


def is_downloaded(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        return handle.read(len(PDF_SIGNATURE)) == PDF_SIGNATURE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.dataset.download")
    parser.add_argument("--metadata", default=DEFAULT_METADATA)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    with Path(arguments.metadata).open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]

    output_dir = Path(arguments.output_dir)
    candidates = [record for record in records if record["selected_part"]]
    pending = [
        record
        for record in candidates
        if not is_downloaded(output_dir / str(record["ident_number"]) / PDF_FILENAME)
    ]
    if arguments.limit:
        pending = pending[: arguments.limit]
    print(f"{len(candidates)} with a public part, {len(pending)} to download")

    client = QuickSearchClient(arguments.delay)
    failures = 0
    for index, record in enumerate(pending, start=1):
        ident_number = record["ident_number"]
        try:
            data = client.download_part(ident_number, record["selected_part"]["token"])
        except Exception as exc:
            failures += 1
            print(f"ERROR {ident_number}: {type(exc).__name__}", file=sys.stderr)
            continue
        target = output_dir / str(ident_number)
        target.mkdir(parents=True, exist_ok=True)
        (target / PDF_FILENAME).write_bytes(data)
        if index % PROGRESS_EVERY == 0:
            print(f"{index}/{len(pending)} downloaded")

    print(f"done: {len(pending) - failures} downloaded, {failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
