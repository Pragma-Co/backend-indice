import argparse
import json
import random
import re
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from scripts.dataset.quicksearch import REQUEST_DELAY_SECONDS, QuickSearchClient, select_part

DEFAULT_LISTING = "training_export/quicksearch/listing.jsonl"
DEFAULT_OUTPUT = "training_export/quicksearch/metadata.jsonl"
SELECTED_FSC_GROUPS = ("59", "53", "47", "61", "95", "80", "68", "16", "91", "31")
EXCLUDED_ID_PATTERN = re.compile(
    r"^(?:QPL|MS\d|ASTM|SAE|ISO|ANSI|NEMA|NAS|NASM|IEC|ASME|AMS|STANAG|AIA|API|IPC|UL|EIA|DIN|BS)"
)
PUBLIC_ID_PATTERN = re.compile(r"^(?:MIL-|A-A-|DOD-|[A-Z]{1,3}-[A-Z]{1,2}-\d)")
ID_PREFIX_PATTERN = re.compile(r"^[A-Z]+(?:-[A-Z]+)?")
FSC_PATTERN = re.compile(r"^\d{4}$")
SAMPLE_SEED = 42
PROGRESS_EVERY = 25


def id_prefix(document_id: str) -> str:
    match = ID_PREFIX_PATTERN.match(document_id)
    return match.group(0) if match else "OTHER"


def sample_rows(rows: list[dict], per_group: int, seed: int = SAMPLE_SEED) -> list[dict]:
    rng = random.Random(seed)
    by_group = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if not FSC_PATTERN.match(row["fsc"]) or row["fsc"][:2] not in SELECTED_FSC_GROUPS:
            continue
        if EXCLUDED_ID_PATTERN.match(row["document_id"]):
            continue
        if not PUBLIC_ID_PATTERN.match(row["document_id"]):
            continue
        by_group[row["fsc"][:2]][id_prefix(row["document_id"])].append(row)

    sampled = []
    for group in SELECTED_FSC_GROUPS:
        buckets = [rng.sample(items, len(items)) for _, items in sorted(by_group[group].items())]
        picked = []
        while len(picked) < per_group and any(buckets):
            for bucket in buckets:
                if bucket and len(picked) < per_group:
                    picked.append(bucket.pop())
        sampled.extend(picked)
    return sampled


def load_done(output: Path) -> set[int]:
    if not output.exists():
        return set()
    with output.open(encoding="utf-8") as handle:
        return {json.loads(line)["ident_number"] for line in handle if line.strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.dataset.details")
    parser.add_argument("--listing", default=DEFAULT_LISTING)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--per-group", type=int, default=60)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS)
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    with Path(arguments.listing).open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    targets = sample_rows(rows, arguments.per_group)
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(output)
    pending = [row for row in targets if row["ident_number"] not in done]
    if arguments.limit:
        pending = pending[: arguments.limit]
    print(f"{len(targets)} sampled, {len(done)} already fetched, {len(pending)} to fetch")

    client = QuickSearchClient(arguments.delay)
    failures = 0
    with output.open("a", encoding="utf-8") as handle:
        for index, row in enumerate(pending, start=1):
            try:
                details = client.fetch_details(row["ident_number"])
            except Exception as exc:
                failures += 1
                print(f"ERROR {row['ident_number']}: {type(exc).__name__}", file=sys.stderr)
                continue
            record = asdict(details)
            selected = select_part(details.parts)
            record["selected_part"] = asdict(selected) if selected else None
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            if index % PROGRESS_EVERY == 0:
                print(f"{index}/{len(pending)} fetched")

    print(f"done: {len(pending) - failures} written to {output}, {failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
