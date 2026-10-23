import argparse
import json
from dataclasses import asdict
from pathlib import Path

from scripts.dataset.quicksearch import REQUEST_DELAY_SECONDS, QuickSearchClient

DEFAULT_OUTPUT = "training_export/quicksearch/listing.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.dataset.listing")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--fsc", default=None)
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")

    client = QuickSearchClient(arguments.delay)
    seen = set()
    with partial.open("w", encoding="utf-8") as handle:
        for page_number, page_count, rows in client.search_active(fsc=arguments.fsc):
            new_rows = [row for row in rows if row.ident_number not in seen]
            for row in new_rows:
                seen.add(row.ident_number)
                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
            handle.flush()
            print(f"page {page_number}/{page_count}: {len(new_rows)} new, {len(seen)} total")
            if arguments.max_pages and page_number >= arguments.max_pages:
                break

    partial.replace(output)
    print(f"{len(seen)} documents written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
