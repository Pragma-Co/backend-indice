import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from classifier.catalog import (
    DEFAULT_CATALOG_PATH,
    load_area_groups,
    load_area_stages,
    load_criteria_version,
)

CRITERIA_DIRECTORY = Path(__file__).parent
DEFAULT_INPUT = "training_export/quicksearch/dataset_unlabeled.csv"
DEFAULT_OUTPUT = "training_export/quicksearch/dataset.csv"
DEFAULT_CACHE = "training_export/quicksearch/area_labels.jsonl"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
MAX_TEXT_CHARS = 6000
NUM_CTX = 8192
REQUEST_TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 10
CSV_FIELD_SIZE_LIMIT = 2**31 - 1
PROGRESS_EVERY = 10
MAX_CONSECUTIVE_UNREACHABLE = 3
MAX_RATE_LIMIT_WAITS = 40
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 10
UNREACHABLE_ERRORS = (urllib.error.URLError, ConnectionError, TimeoutError)

Transport = Callable[[str, dict, dict, int], dict]


class InvalidLabelError(Exception):
    pass


def criteria_path(criteria_version: str) -> Path:
    return CRITERIA_DIRECTORY / f"area_criteria_v{criteria_version}.md"


def area_key(
    text: str,
    criteria_version: str,
    model: str,
    max_chars: int = MAX_TEXT_CHARS,
    title: str = "",
) -> str:
    payload = "\n".join([criteria_version, model, title, text[:max_chars]])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def http_post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class AreaCache:
    def __init__(self, path):
        self.path = Path(path)
        self.labels = {}
        self.models = {}
        if self.path.is_file():
            with self.path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        record = json.loads(line)
                        self.labels[record["key"]] = record["label"]
                        if record.get("model"):
                            self.models[record["key"]] = record["model"]

    def get(self, key: str) -> str | None:
        return self.labels.get(key)

    def put(self, key: str, label: str, document_id: str, model: str | None = None) -> None:
        self.labels[key] = label
        if model:
            self.models[key] = model
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            record = {"key": key, "label": label, "document_id": document_id, "model": model}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class OllamaAreaLabeler:
    def __init__(
        self,
        base_url: str,
        model: str,
        criteria: str,
        labels: frozenset[str],
        token: str | None = None,
        max_chars: int = MAX_TEXT_CHARS,
        transport: Transport = http_post_json,
    ):
        self.url = base_url.rstrip("/") + "/api/chat"
        self.model = model
        self.criteria = criteria
        self.labels = labels
        self.max_chars = max_chars
        self.transport = transport
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def request_payload(self, text: str, title: str = "") -> dict:
        excerpt = text[: self.max_chars]
        content = f"Title: {title}\n\n{excerpt}" if title else excerpt
        return {
            "model": self.model,
            "stream": False,
            "format": {
                "type": "object",
                "properties": {"stage": {"type": "string", "enum": sorted(self.labels)}},
                "required": ["stage"],
            },
            "options": {"temperature": 0, "num_ctx": NUM_CTX},
            "messages": [
                {"role": "system", "content": self.criteria},
                {"role": "user", "content": content},
            ],
        }

    def label(self, text: str, title: str = "") -> str:
        response = self.transport(
            self.url, self.request_payload(text, title), self.headers, REQUEST_TIMEOUT_SECONDS
        )
        return self.parse((response.get("message") or {}).get("content") or "")

    def parse(self, answer: str) -> str:
        try:
            stage = json.loads(answer)["stage"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise InvalidLabelError(f"unreadable answer: {answer!r}") from exc
        if stage not in self.labels:
            raise InvalidLabelError(f"stage {stage!r} is not in the area catalog")
        return stage


@dataclass
class LabelingResult:
    labels: list[str | None]
    models: list[str | None] = field(default_factory=list)
    calls: int = 0
    cached: int = 0
    failures: list[str] = field(default_factory=list)
    aborted: str | None = None


def rate_limit_wait_seconds(error) -> float:
    headers = getattr(getattr(error, "response", None), "headers", None) or {}
    value = headers.get("retry-after")
    try:
        return max(float(value), 1.0)
    except (TypeError, ValueError):
        return DEFAULT_RATE_LIMIT_WAIT_SECONDS


class GroqAreaLabeler:
    def __init__(
        self,
        client,
        model: str,
        criteria: str,
        labels: frozenset[str],
        max_chars: int = MAX_TEXT_CHARS,
        sleep=time.sleep,
        fallback_model: str | None = None,
    ):
        self.client = client
        self.model = model
        self.criteria = criteria
        self.labels = labels
        self.max_chars = max_chars
        self.sleep = sleep
        self.fallback_models = [m for m in (fallback_model or "").split(",") if m]
        self.last_model = model

    def label(self, text: str, title: str = "") -> str:
        excerpt = text[: self.max_chars]
        content = f"Title: {title}" + chr(10) + chr(10) + excerpt if title else excerpt
        models = [self.model, *self.fallback_models]
        for _ in range(MAX_RATE_LIMIT_WAITS):
            wait = None
            for model in models:
                try:
                    response = self._ask(model, content)
                except Exception as exc:
                    if type(exc).__name__ != "RateLimitError":
                        raise
                    seconds = rate_limit_wait_seconds(exc)
                    wait = seconds if wait is None else min(wait, seconds)
                    continue
                self.last_model = model
                return OllamaAreaLabeler.parse(self, response.choices[0].message.content or "")
            self.sleep(wait)
        raise RuntimeError("rate limited for too long")

    def _ask(self, model: str, content: str):
        return self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": self.criteria},
                {"role": "user", "content": content},
            ],
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
        )


def build_labeler(
    provider: str,
    criteria: str,
    stages: frozenset[str],
    max_chars: int,
    fallback_model: str | None = None,
):
    if provider == "groq":
        import groq

        model = os.environ["GROQ_MODEL"]
        client = groq.Groq(api_key=os.environ["GROQ_API_KEY"])
        labeler = GroqAreaLabeler(
            client, model, criteria, stages, max_chars=max_chars, fallback_model=fallback_model
        )
        return labeler, model
    model = os.environ["OLLAMA_MODEL"]
    labeler = OllamaAreaLabeler(
        os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL),
        model,
        criteria,
        stages,
        token=os.environ.get("OLLAMA_API_TOKEN"),
        max_chars=max_chars,
    )
    return labeler, model


def label_rows(
    rows,
    labeler,
    cache: AreaCache,
    criteria_version: str,
    model: str,
    sleep=time.sleep,
    max_chars: int = MAX_TEXT_CHARS,
    progress: Callable[[int, int], None] | None = None,
):
    result = LabelingResult(labels=[])
    consecutive_unreachable = 0
    for position, row in enumerate(rows, start=1):
        if progress:
            progress(position, len(rows))
        title = row.get("title", "")
        key = area_key(row["text"], criteria_version, model, max_chars, title)
        label = cache.get(key)
        if label is not None:
            result.cached += 1
            result.labels.append(label)
            result.models.append(cache.models.get(key, model))
            continue

        label = None
        unreachable = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result.calls += 1
                label = labeler.label(row["text"], title)
                break
            except InvalidLabelError as exc:
                error = str(exc)
                unreachable = False
            except Exception as exc:
                error = type(exc).__name__
                unreachable = isinstance(exc, UNREACHABLE_ERRORS)
                if attempt < MAX_ATTEMPTS:
                    sleep(RETRY_BACKOFF_SECONDS * attempt)
        used_model = getattr(labeler, "last_model", model) if label else None
        if label is None:
            result.failures.append(f"{row['document_id']}: {error}")
        else:
            cache.put(key, label, row["document_id"], used_model)
        result.labels.append(label)
        result.models.append(used_model)

        consecutive_unreachable = consecutive_unreachable + 1 if unreachable else 0
        if consecutive_unreachable >= MAX_CONSECUTIVE_UNREACHABLE:
            result.aborted = f"the labeling service failed {consecutive_unreachable} "
            + "documents in a row ({error})"
            result.labels.extend([None] * (len(rows) - len(result.labels)))
            result.models.extend([None] * (len(rows) - len(result.models)))
            break
    return result


def read_rows(path) -> tuple[list[str], list[dict]]:
    csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def build_output(
    rows: list[dict],
    labels: list[str | None],
    groups: dict[str, str],
    columns: list[str],
    models: list[str | None] | None = None,
) -> tuple[list[str], list[dict]]:
    models = models or [None] * len(labels)
    labeled = [
        {**row, "area_stage": stage, "area": groups[stage], "area_model": used or ""}
        for row, stage, used in zip(rows, labels, models, strict=True)
        if stage
    ]
    output_columns = list(columns)
    for extra in ("area_stage", "area_model"):
        if extra not in output_columns:
            output_columns.append(extra)
    return output_columns, labeled


def filter_rows(rows: list[dict], document_ids: set[str]) -> list[dict]:
    return [row for row in rows if row["document_id"] in document_ids]


def print_progress(position: int, total: int) -> None:
    if position == 1 or position % PROGRESS_EVERY == 0 or position == total:
        print(f"{position}/{total} at {time.strftime('%H:%M:%S')}", flush=True)


def write_rows(path, columns: list[str], rows: list[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.dataset.label_areas")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-chars", type=int, default=MAX_TEXT_CHARS)
    parser.add_argument("--provider", choices=("ollama", "groq"), default="ollama")
    parser.add_argument(
        "--fallback-model",
        default=None,
        help="Groq model(s), comma separated, tried in order when the main model is rate limited.",
    )
    parser.add_argument(
        "--criteria-version",
        default=None,
        help="Criteria file to use instead of the version the catalog names.",
    )
    parser.add_argument(
        "--documents-from",
        default=None,
        help="CSV with a document_id column; only those documents are labeled.",
    )
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    stages = load_area_stages(arguments.catalog)
    groups = load_area_groups(arguments.catalog)
    criteria_version = arguments.criteria_version or load_criteria_version(arguments.catalog)
    labeler, model = build_labeler(
        arguments.provider,
        criteria_path(criteria_version).read_text(encoding="utf-8"),
        stages,
        arguments.max_chars,
        fallback_model=arguments.fallback_model,
    )

    columns, rows = read_rows(arguments.input)
    if arguments.documents_from:
        _, wanted = read_rows(arguments.documents_from)
        rows = filter_rows(rows, {row["document_id"] for row in wanted})
    if arguments.limit:
        rows = rows[: arguments.limit]
    result = label_rows(
        rows,
        labeler,
        AreaCache(arguments.cache),
        criteria_version,
        model,
        max_chars=arguments.max_chars,
        progress=print_progress,
    )

    output_columns, labeled = build_output(rows, result.labels, groups, columns, result.models)
    write_rows(arguments.output, output_columns, labeled)
    print(
        f"{len(labeled)} labeled ({result.cached} from cache, {result.calls} calls), "
        f"{len(result.failures)} failures"
    )
    for failure in result.failures:
        print(f"ERROR {failure}", file=sys.stderr)
    if result.aborted:
        print(
            f"ABORTED: {result.aborted}. Labels so far are cached; rerun when the service is back.",
            file=sys.stderr,
        )
        return 2
    return 0 if not result.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
