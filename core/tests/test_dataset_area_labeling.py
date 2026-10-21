import json
import tempfile
import urllib.error
from pathlib import Path

from django.test import SimpleTestCase

from classifier.catalog import load_area_groups, load_area_stages, load_criteria_version
from scripts.dataset.label_areas import (
    CRITERIA_DIRECTORY,
    DEFAULT_RATE_LIMIT_WAIT_SECONDS,
    MAX_ATTEMPTS,
    MAX_TEXT_CHARS,
    NUM_CTX,
    AreaCache,
    GroqAreaLabeler,
    InvalidLabelError,
    OllamaAreaLabeler,
    area_key,
    build_output,
    build_parser,
    criteria_path,
    filter_rows,
    label_rows,
    rate_limit_wait_seconds,
)

AREA_LABELS = load_area_stages()


class BuildOutputTests(SimpleTestCase):
    def build(self, labels, columns=("text", "document_id", "area")):
        rows = [
            {"text": "t", "document_id": f"DOC-{index}", "area": ""} for index in range(len(labels))
        ]
        return build_output(rows, labels, load_area_groups(), list(columns))

    def test_should_keep_the_fine_stage_and_add_the_merged_area_class(self):
        _, rows = self.build(["DESIGN", "PROCESSING", "NO_CLEAR_STAGE", "MATERIALS"])

        self.assertEqual(
            [(row["area_stage"], row["area"]) for row in rows],
            [
                ("DESIGN", "DESIGN"),
                ("PROCESSING", "OTHER_STAGE"),
                ("NO_CLEAR_STAGE", "OTHER_STAGE"),
                ("MATERIALS", "MATERIALS"),
            ],
        )

    def test_should_skip_documents_that_could_not_be_labeled(self):
        _, rows = self.build(["DESIGN", None, "INSPECTION_TEST"])

        self.assertEqual([row["document_id"] for row in rows], ["DOC-0", "DOC-2"])

    def test_should_add_the_stage_column_once(self):
        columns, _ = self.build(["DESIGN"], columns=("text", "document_id", "area", "area_stage"))

        self.assertEqual(columns.count("area_stage"), 1)

    def test_should_append_the_stage_column_when_the_input_has_none(self):
        columns, _ = self.build(["DESIGN"])

        self.assertEqual(columns[-2:], ["area_stage", "area_model"])


class FilterRowsTests(SimpleTestCase):
    def test_should_keep_only_the_listed_documents_in_the_original_order(self):
        all_rows = [{"document_id": f"DOC-{index}", "text": "t"} for index in range(5)]

        kept = filter_rows(all_rows, {"DOC-3", "DOC-1"})

        self.assertEqual([row["document_id"] for row in kept], ["DOC-1", "DOC-3"])

    def test_should_return_nothing_when_no_listed_document_exists(self):
        self.assertEqual(filter_rows([{"document_id": "DOC-0", "text": "t"}], {"OTHER"}), [])


class LabelRowsUnreachableServiceTests(SimpleTestCase):
    def cache(self) -> AreaCache:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        return AreaCache(directory / "labels.jsonl")

    def down(self, call, text):
        raise urllib.error.URLError("connection refused")

    def test_should_stop_after_three_documents_in_a_row_cannot_reach_the_service(self):
        labeler = FakeLabeler(self.down)

        result = label_rows(rows(10), labeler, self.cache(), "1", "m", sleep=lambda _s: None)

        self.assertIsNotNone(result.aborted)
        self.assertEqual(len(result.failures), 3)
        self.assertEqual(labeler.calls, 3 * MAX_ATTEMPTS)

    def test_should_keep_one_label_slot_per_row_even_when_aborted(self):
        result = label_rows(
            rows(10), FakeLabeler(self.down), self.cache(), "1", "m", sleep=lambda _s: None
        )

        self.assertEqual(result.labels, [None] * 10)

    def test_should_not_abort_when_the_service_comes_back_between_failures(self):
        def flaky(call, text):
            if call <= 2 * MAX_ATTEMPTS:
                raise urllib.error.URLError("timeout")
            return "DESIGN"

        result = label_rows(
            rows(4), FakeLabeler(flaky), self.cache(), "1", "m", sleep=lambda _s: None
        )

        self.assertIsNone(result.aborted)
        self.assertEqual(result.labels.count("DESIGN"), 2)

    def test_should_not_abort_for_answers_that_are_only_invalid_labels(self):
        def invalid(call, text):
            raise InvalidLabelError("stage 'X' is not in the area catalog")

        result = label_rows(
            rows(6), FakeLabeler(invalid), self.cache(), "1", "m", sleep=lambda _s: None
        )

        self.assertIsNone(result.aborted)
        self.assertEqual(len(result.failures), 6)


class LabelRowsProgressTests(SimpleTestCase):
    def test_should_report_progress_for_cached_and_new_rows_alike(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        cache = AreaCache(directory / "labels.jsonl")
        seen = []
        labeler = FakeLabeler(lambda call, text: "DESIGN")
        label_rows(rows(1), labeler, cache, "1", "m", sleep=lambda _s: None)

        label_rows(
            rows(3),
            labeler,
            cache,
            "1",
            "m",
            sleep=lambda _s: None,
            progress=lambda position, total: seen.append((position, total)),
        )

        self.assertEqual(seen, [(1, 3), (2, 3), (3, 3)])


class FakeLabeler:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = 0

    def label(self, text: str, title: str = "") -> str:
        self.calls += 1
        return self.behaviour(self.calls, text)


def rows(count: int = 3) -> list[dict]:
    return [
        {"text": f"document text {index}", "document_id": f"DOC-{index}"} for index in range(count)
    ]


def no_sleep(_seconds):
    return None


class LabelRowsTests(SimpleTestCase):
    def cache(self) -> AreaCache:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        return AreaCache(directory / "labels.jsonl")

    def test_should_label_every_row_and_remember_the_answers(self):
        cache = self.cache()
        labeler = FakeLabeler(lambda call, text: "DESIGN")

        result = label_rows(rows(), labeler, cache, "1", "model-x", sleep=no_sleep)

        self.assertEqual(result.labels, ["DESIGN"] * 3)
        self.assertEqual((result.calls, result.cached), (3, 0))

    def test_should_not_call_the_service_again_for_cached_rows(self):
        cache = self.cache()
        first = FakeLabeler(lambda call, text: "PROCESSING")
        label_rows(rows(), first, cache, "1", "model-x", sleep=no_sleep)
        second = FakeLabeler(lambda call, text: "DESIGN")

        result = label_rows(rows(), second, cache, "1", "model-x", sleep=no_sleep)

        self.assertEqual(second.calls, 0)
        self.assertEqual(result.labels, ["PROCESSING"] * 3)
        self.assertEqual(result.cached, 3)

    def test_should_keep_the_cache_across_runs_on_disk(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = directory / "labels.jsonl"
        label_rows(
            rows(1), FakeLabeler(lambda c, t: "MATERIALS"), AreaCache(path), "1", "m", no_sleep
        )

        reloaded = AreaCache(path)

        key = area_key("document text 0", "1", "m")
        self.assertEqual(reloaded.get(key), "MATERIALS")
        self.assertEqual(json.loads(path.read_text().splitlines()[0])["document_id"], "DOC-0")

    def test_should_relabel_when_the_criteria_version_changes(self):
        cache = self.cache()
        label_rows(rows(1), FakeLabeler(lambda c, t: "DESIGN"), cache, "1", "m", no_sleep)
        labeler = FakeLabeler(lambda call, text: "PROCESSING")

        result = label_rows(rows(1), labeler, cache, "2", "m", no_sleep)

        self.assertEqual(labeler.calls, 1)
        self.assertEqual(result.labels, ["PROCESSING"])

    def test_should_retry_a_transient_error_and_then_succeed(self):
        def behaviour(call, text):
            if call == 1:
                raise RuntimeError("timeout")
            return "INSPECTION_TEST"

        labeler = FakeLabeler(behaviour)

        result = label_rows(rows(1), labeler, self.cache(), "1", "m", no_sleep)

        self.assertEqual(result.labels, ["INSPECTION_TEST"])
        self.assertEqual(result.calls, 2)

    def test_should_report_an_invalid_label_as_a_failure_without_caching_it(self):
        def behaviour(call, text):
            raise InvalidLabelError("stage 'ASSEMBLY' is not in the area catalog")

        cache = self.cache()

        result = label_rows(rows(1), FakeLabeler(behaviour), cache, "1", "m", no_sleep)

        self.assertEqual(result.labels, [None])
        self.assertEqual(len(result.failures), 1)
        self.assertIn("DOC-0", result.failures[0])
        self.assertIsNone(cache.get(area_key("document text 0", "1", "m")))

    def test_should_relabel_when_the_title_changes(self):
        cache = self.cache()
        row = {"text": "same text", "document_id": "DOC-1", "title": "First title"}
        label_rows([row], FakeLabeler(lambda c, t: "DESIGN"), cache, "1", "m", no_sleep)
        labeler = FakeLabeler(lambda call, text: "MATERIALS")

        result = label_rows([{**row, "title": "Other title"}], labeler, cache, "1", "m", no_sleep)

        self.assertEqual(labeler.calls, 1)
        self.assertEqual(result.labels, ["MATERIALS"])

    def test_should_only_use_the_start_of_the_text_in_the_cache_key(self):
        shared = "x" * MAX_TEXT_CHARS

        first = area_key(shared + "tail one", "1", "m")
        second = area_key(shared + "tail two", "1", "m")

        self.assertEqual(first, second)


class RecordingTransport:
    def __init__(self, answer: str = '{"stage": "DESIGN"}'):
        self.answer = answer
        self.requests = []

    def __call__(self, url, payload, headers, timeout):
        self.requests.append({"url": url, "payload": payload, "headers": headers})
        return {"message": {"content": self.answer}}


class OllamaAreaLabelerRequestTests(SimpleTestCase):
    def labeler(self, transport, **options) -> OllamaAreaLabeler:
        return OllamaAreaLabeler(
            "http://vm.example:11434/",
            "qwen-test",
            "the criteria",
            AREA_LABELS,
            transport=transport,
            **options,
        )

    def test_should_call_the_chat_endpoint_without_streaming_and_with_zero_temperature(self):
        transport = RecordingTransport()

        self.labeler(transport).label("some text")

        request = transport.requests[0]
        self.assertEqual(request["url"], "http://vm.example:11434/api/chat")
        self.assertEqual(request["payload"]["model"], "qwen-test")
        self.assertIs(request["payload"]["stream"], False)
        self.assertEqual(request["payload"]["options"], {"temperature": 0, "num_ctx": NUM_CTX})

    def test_should_constrain_the_answer_to_the_catalog_stages(self):
        transport = RecordingTransport()

        self.labeler(transport).label("some text")

        schema = transport.requests[0]["payload"]["format"]
        self.assertEqual(schema["properties"]["stage"]["enum"], sorted(AREA_LABELS))
        self.assertEqual(schema["required"], ["stage"])

    def test_should_send_the_criteria_as_system_message_and_the_truncated_text_as_user(self):
        transport = RecordingTransport()

        self.labeler(transport, max_chars=10).label("0123456789-cut")

        messages = transport.requests[0]["payload"]["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "the criteria"})
        self.assertEqual(messages[1], {"role": "user", "content": "0123456789"})

    def test_should_put_the_title_before_the_text_in_the_user_message(self):
        transport = RecordingTransport()

        self.labeler(transport, max_chars=10).label("0123456789-cut", title="Cable, Coaxial")

        content = transport.requests[0]["payload"]["messages"][1]["content"]
        self.assertEqual(content, "Title: Cable, Coaxial\n\n0123456789")

    def test_should_send_the_token_only_when_one_is_configured(self):
        with_token, without_token = RecordingTransport(), RecordingTransport()

        self.labeler(with_token, token="secret").label("text")
        self.labeler(without_token).label("text")

        self.assertEqual(with_token.requests[0]["headers"], {"Authorization": "Bearer secret"})
        self.assertEqual(without_token.requests[0]["headers"], {})

    def test_should_return_the_stage_from_the_response(self):
        transport = RecordingTransport('{"stage": "INSPECTION_TEST"}')

        self.assertEqual(self.labeler(transport).label("text"), "INSPECTION_TEST")

    def test_should_treat_an_empty_response_as_an_invalid_label(self):
        def empty(url, payload, headers, timeout):
            return {}

        with self.assertRaises(InvalidLabelError):
            self.labeler(empty).label("text")


class OllamaAreaLabelerParsingTests(SimpleTestCase):
    def labeler(self) -> OllamaAreaLabeler:
        return OllamaAreaLabeler("http://localhost:11434", "m", "criteria", AREA_LABELS)

    def test_should_accept_a_stage_from_the_catalog(self):
        self.assertEqual(self.labeler().parse('{"stage": "PROCESSING"}'), "PROCESSING")

    def test_should_reject_a_stage_outside_the_catalog(self):
        with self.assertRaises(InvalidLabelError):
            self.labeler().parse('{"stage": "ASSEMBLY"}')

    def test_should_reject_an_answer_that_is_not_json(self):
        with self.assertRaises(InvalidLabelError):
            self.labeler().parse("PROCESSING")

    def test_should_reject_json_without_the_stage_key(self):
        with self.assertRaises(InvalidLabelError):
            self.labeler().parse('{"label": "DESIGN"}')


class CriteriaFileTests(SimpleTestCase):
    def test_should_ship_a_criteria_file_for_the_catalog_version(self):
        path = criteria_path(load_criteria_version())

        self.assertTrue(path.is_file())

    def test_should_describe_every_area_class_in_every_criteria_version(self):
        files = sorted(CRITERIA_DIRECTORY.glob("area_criteria_v*.md"))

        missing = {
            file.name: [label for label in AREA_LABELS if label not in file.read_text("utf-8")]
            for file in files
        }

        self.assertGreaterEqual(len(files), 2)
        self.assertEqual({name: labels for name, labels in missing.items() if labels}, {})

    def test_should_ask_every_criteria_version_for_the_json_answer_the_parser_reads(self):
        for file in CRITERIA_DIRECTORY.glob("area_criteria_v*.md"):
            self.assertIn('{"stage": "<STAGE>"}', file.read_text(encoding="utf-8"), file.name)


class CriteriaVersionOptionTests(SimpleTestCase):
    def test_should_default_to_the_version_named_by_the_catalog(self):
        arguments = build_parser().parse_args([])

        self.assertIsNone(arguments.criteria_version)

    def test_should_accept_an_explicit_criteria_version(self):
        arguments = build_parser().parse_args(["--criteria-version", "2"])

        self.assertEqual(arguments.criteria_version, "2")
        self.assertTrue(criteria_path("2").is_file())


class FakeGroqClient:
    def __init__(self, answer='{"stage": "MATERIALS"}'):
        self.answer = answer
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Message", (), {"content": self.answer})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class GroqAreaLabelerTests(SimpleTestCase):
    def labeler(self, client, **options) -> GroqAreaLabeler:
        return GroqAreaLabeler(client, "llama-test", "the criteria", AREA_LABELS, **options)

    def test_should_ask_for_json_at_zero_temperature_with_the_criteria_as_system_message(self):
        client = FakeGroqClient()

        stage = self.labeler(client, max_chars=5).label("0123456789", title="A title")

        call = client.calls[0]
        self.assertEqual(stage, "MATERIALS")
        self.assertEqual(call["model"], "llama-test")
        self.assertEqual(call["temperature"], 0)
        self.assertEqual(call["response_format"], {"type": "json_object"})
        self.assertEqual(call["messages"][0], {"role": "system", "content": "the criteria"})
        self.assertEqual(call["messages"][1]["content"], "Title: A title\n\n01234")

    def test_should_reject_a_stage_outside_the_catalog(self):
        with self.assertRaises(InvalidLabelError):
            self.labeler(FakeGroqClient('{"stage": "ASSEMBLY"}')).label("text")

    def test_should_default_the_provider_to_ollama(self):
        self.assertEqual(build_parser().parse_args([]).provider, "ollama")
        self.assertEqual(build_parser().parse_args(["--provider", "groq"]).provider, "groq")


class RateLimitError(Exception):
    def __init__(self, retry_after=None):
        super().__init__("429")
        self.response = type(
            "Response", (), {"headers": {"retry-after": retry_after} if retry_after else {}}
        )()


class GroqRateLimitTests(SimpleTestCase):
    def test_should_wait_the_time_the_service_asks_for_and_retry(self):
        client = FakeGroqClient()
        answers = [RateLimitError("3.5"), RateLimitError(), None]
        original = client.create

        def create(**kwargs):
            error = answers.pop(0)
            if error:
                raise error
            return original(**kwargs)

        client.create = create
        waits = []
        labeler = GroqAreaLabeler(client, "m", "c", AREA_LABELS, sleep=waits.append)

        stage = labeler.label("text")

        self.assertEqual(stage, "MATERIALS")
        self.assertEqual(waits, [3.5, DEFAULT_RATE_LIMIT_WAIT_SECONDS])

    def test_should_not_swallow_other_errors(self):
        client = FakeGroqClient()
        client.create = lambda **kwargs: (_ for _ in ()).throw(ValueError("boom"))

        with self.assertRaises(ValueError):
            GroqAreaLabeler(client, "m", "c", AREA_LABELS, sleep=lambda s: None).label("text")

    def test_should_read_a_missing_header_as_the_default_wait(self):
        self.assertEqual(rate_limit_wait_seconds(RateLimitError()), DEFAULT_RATE_LIMIT_WAIT_SECONDS)
        self.assertEqual(rate_limit_wait_seconds(RateLimitError("0.2")), 1.0)


class GroqFallbackModelTests(SimpleTestCase):
    def client_limited_on(self, limited_model: str) -> FakeGroqClient:
        client = FakeGroqClient()
        original = client.create

        def create(**kwargs):
            if kwargs["model"] == limited_model:
                raise RateLimitError("5")
            return original(**kwargs)

        client.create = create
        return client

    def test_should_use_the_fallback_model_without_waiting_when_the_main_one_is_limited(self):
        client = self.client_limited_on("main")
        waits = []
        labeler = GroqAreaLabeler(
            client, "main", "c", AREA_LABELS, sleep=waits.append, fallback_model="spare"
        )

        stage = labeler.label("text")

        self.assertEqual((stage, labeler.last_model, waits), ("MATERIALS", "spare", []))

    def test_should_prefer_the_main_model_when_it_is_available(self):
        labeler = GroqAreaLabeler(
            FakeGroqClient(), "main", "c", AREA_LABELS, fallback_model="spare"
        )

        labeler.label("text")

        self.assertEqual(labeler.last_model, "main")

    def test_should_wait_when_both_models_are_limited(self):
        client = FakeGroqClient()
        state = {"calls": 0}
        original = client.create

        def create(**kwargs):
            state["calls"] += 1
            if state["calls"] <= 2:
                raise RateLimitError("4")
            return original(**kwargs)

        client.create = create
        waits = []
        labeler = GroqAreaLabeler(
            client, "main", "c", AREA_LABELS, sleep=waits.append, fallback_model="spare"
        )

        labeler.label("text")

        self.assertEqual(waits, [4.0])

    def test_should_record_which_model_labeled_each_document(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        cache = AreaCache(directory / "labels.jsonl")
        labeler = GroqAreaLabeler(
            self.client_limited_on("main"), "main", "c", AREA_LABELS, fallback_model="spare"
        )

        result = label_rows(rows(2), labeler, cache, "2", "main", sleep=lambda s: None)
        again = label_rows(
            rows(2),
            labeler,
            AreaCache(directory / "labels.jsonl"),
            "2",
            "main",
            sleep=lambda s: None,
        )
        _, output = build_output(
            rows(2), again.labels, load_area_groups(), ["text", "document_id"], again.models
        )

        self.assertEqual(result.models, ["spare", "spare"])
        self.assertEqual(again.models, ["spare", "spare"])
        self.assertEqual(output[0]["area_model"], "spare")
