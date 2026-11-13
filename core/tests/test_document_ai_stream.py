import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import Client, TestCase, override_settings

from core.models import Area, Discipline, DocumentType, User
from core.services.document_ai_service import prepare_suggestion, stream_suggestion_events
from core.tests.test_document_ai_service import NULL_SUGGESTION, TEMP_FILE_ID, predictions

STREAMED_TITLE = "Memorial de Cálculo da Longarina Principal da Asa Esquerda do Avião"
STREAMED_DESCRIPTION = "Dimensiona a longarina principal considerando as cargas de voo previstas."


def answer_pieces(answer=None, size=9):
    answer = answer or json.dumps({"resumo": STREAMED_DESCRIPTION, "titulo": STREAMED_TITLE})
    return [answer[start : start + size] for start in range(0, len(answer), size)]


def streamed_events():
    return list(stream_suggestion_events(TEMP_FILE_ID, prepare_suggestion(TEMP_FILE_ID)))


def text_values(events, field):
    return [
        event["value"] for event in events if event["type"] == "text" and event["field"] == field
    ]


@mock.patch("core.services.document_ai_service.get_mongo_db")
@mock.patch(
    "core.services.document_ai_service.get_temp_upload_record",
    return_value={"extracted_text": "texto processado"},
)
@mock.patch("core.services.document_ai_service.get_classifier")
class StreamSuggestionEventsTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.settings_override = override_settings(TEMP_UPLOAD_DIR=self.temp_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.ollama = mock.patch(
            "core.services.document_ai_service.stream_ollama",
            return_value=iter(answer_pieces()),
        ).start()
        self.addCleanup(mock.patch.stopall)

        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        DocumentType.objects.create(code="ESP", name="Especificação Técnica")
        Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        (Path(self.temp_dir) / f"{TEMP_FILE_ID}.pdf").write_bytes(b"conteudo")

    def test_given_streamed_answer_when_iterated_then_sends_classification_text_and_done(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_classifier.return_value.predict.return_value = predictions()

        events = streamed_events()

        self.assertEqual(events[0]["type"], "classification")
        self.assertEqual(
            events[0]["suggestion"]["discipline"], {"id": self.discipline.id, "name": "Estruturas"}
        )
        self.assertIsNone(events[0]["suggestion"]["title"])
        self.assertEqual({event["type"] for event in events[1:-1]}, {"text"})
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["suggestion"]["title"], STREAMED_TITLE)
        self.assertEqual(events[-1]["suggestion"]["description"], STREAMED_DESCRIPTION)
        self.assertEqual(
            events[-1]["suggestion"]["discipline"],
            {"id": self.discipline.id, "name": "Estruturas"},
        )

    def test_given_streamed_answer_when_iterated_then_each_field_grows_until_complete(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_classifier.return_value.predict.return_value = predictions()

        events = streamed_events()

        for field, complete in (("title", STREAMED_TITLE), ("description", STREAMED_DESCRIPTION)):
            values = text_values(events, field)
            self.assertGreater(len(values), 1)
            self.assertEqual(values[-1], complete)
            self.assertEqual(values, sorted(values, key=len))
            for value in values:
                self.assertTrue(complete.startswith(value))

    def test_given_code_on_the_first_page_when_iterated_then_every_title_snapshot_starts_with_it(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_classifier.return_value.predict.return_value = predictions()
        mock_record.return_value = {
            "extracted_text": "texto processado",
            "title_excerpt": "MIL-STD-883K TEST METHOD STANDARD",
            "content_excerpt": "",
        }

        events = streamed_events()

        titles = text_values(events, "title")
        self.assertGreater(len(titles), 1)
        for title in titles:
            self.assertTrue(title.startswith("MIL-STD-883K - "))
        self.assertEqual(events[-1]["suggestion"]["title"], f"MIL-STD-883K - {STREAMED_TITLE}")

    def test_given_unfinished_value_when_iterated_then_holds_back_the_tail_at_a_word_boundary(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_classifier.return_value.predict.return_value = predictions()
        self.ollama.return_value = iter([json.dumps({"titulo": STREAMED_TITLE})[:-2]])

        events = streamed_events()

        shown = text_values(events, "title")[0]
        self.assertTrue(STREAMED_TITLE.startswith(shown + " "))
        self.assertGreaterEqual(len(STREAMED_TITLE) - len(shown), 24)

    def test_given_email_split_across_pieces_when_iterated_then_never_sends_any_part_of_it(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_classifier.return_value.predict.return_value = predictions()
        answer = json.dumps(
            {
                "titulo": "Relatório de ensaio estrutural da asa",
                "resumo": "Contato do responsável: ana.souza@example.com para dúvidas sobre o "
                "ensaio realizado em bancada.",
            }
        )
        self.ollama.return_value = iter(answer_pieces(answer, size=3))

        events = streamed_events()

        sent = json.dumps(events, ensure_ascii=False)
        self.assertNotIn("ana.souza", sent)
        self.assertNotIn("example.com", sent)
        self.assertIn("[REDACTED]", events[-1]["suggestion"]["description"])

    def test_given_ollama_fails_midway_when_iterated_then_finishes_with_null_text(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_classifier.return_value.predict.return_value = predictions()

        def broken_stream(*args, **kwargs):
            yield from answer_pieces()[:6]
            raise OSError("connection reset")

        self.ollama.side_effect = broken_stream

        events = streamed_events()

        self.assertEqual(events[-1]["type"], "done")
        self.assertIsNone(events[-1]["suggestion"]["title"])
        self.assertIsNone(events[-1]["suggestion"]["description"])
        self.assertEqual(events[-1]["suggestion"]["discipline"]["name"], "Estruturas")

    def test_given_no_extracted_text_when_iterated_then_skips_ollama(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_record.return_value = {"extracted_text": "  "}

        events = streamed_events()

        self.assertEqual([event["type"] for event in events], ["classification", "done"])
        self.assertEqual(events[-1]["suggestion"], NULL_SUGGESTION)
        self.ollama.assert_not_called()

    def test_given_streamed_answer_when_iterated_then_saves_classification_first_and_text_last(
        self, mock_classifier, mock_record, mock_mongo
    ):
        mock_classifier.return_value.predict.return_value = predictions()

        events = streamed_events()

        saved = [
            call.args[1]["$set"]["ai_suggestion"]
            for call in mock_mongo.return_value.__getitem__.return_value.update_one.call_args_list
        ]
        self.assertEqual(len(saved), 2)
        self.assertIsNone(saved[0]["title"])
        self.assertEqual(saved[0]["discipline"]["name"], "Estruturas")
        self.assertEqual(saved[1], events[-1]["suggestion"])


@mock.patch("core.services.document_ai_service.get_mongo_db")
@mock.patch(
    "core.services.document_ai_service.get_temp_upload_record",
    return_value={"extracted_text": "texto processado"},
)
@mock.patch("core.services.document_ai_service.get_classifier")
class StreamDocumentSuggestionsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.settings_override = override_settings(TEMP_UPLOAD_DIR=self.temp_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.ollama = mock.patch(
            "core.services.document_ai_service.stream_ollama",
            return_value=iter(answer_pieces()),
        ).start()
        self.addCleanup(mock.patch.stopall)

        Discipline.objects.create(code="EST", name="Estruturas")
        DocumentType.objects.create(code="ESP", name="Especificação Técnica")
        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.client.force_login(
            User.objects.create_user(
                email="author@example.com", password="secret", name="Author", area=area
            )
        )

    def _temp_file(self, extension="pdf"):
        path = Path(self.temp_dir) / f"{TEMP_FILE_ID}.{extension}"
        path.write_bytes(b"conteudo")
        return path

    def _events(self, response):
        body = b"".join(response.streaming_content).decode("utf-8")
        return [json.loads(line) for line in body.splitlines()]

    def test_given_valid_pdf_when_posted_then_streams_one_json_event_per_line(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions()

        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions/stream")

        events = self._events(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/x-ndjson")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual(events[0]["type"], "classification")
        self.assertEqual(set(events[0]["suggestion"]), set(NULL_SUGGESTION))
        self.assertEqual(events[0]["suggestion"]["discipline"]["name"], "Estruturas")
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["suggestion"]["title"], STREAMED_TITLE)
        self.assertEqual(events[-1]["suggestion"]["description"], STREAMED_DESCRIPTION)

    def test_given_missing_temp_file_when_posted_then_returns_404(
        self, mock_classifier, mock_record, mock_mongo
    ):
        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions/stream")

        self.assertEqual(response.status_code, 404)

    def test_given_unsupported_extension_when_posted_then_returns_422(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file(extension="png")

        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions/stream")

        self.assertEqual(response.status_code, 422)

    def test_given_get_request_when_called_then_returns_405(
        self, mock_classifier, mock_record, mock_mongo
    ):
        response = self.client.get(f"/documents/{TEMP_FILE_ID}/suggestions/stream")

        self.assertEqual(response.status_code, 405)

    def test_given_anonymous_user_when_posted_then_returns_401(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        self.client.logout()

        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions/stream")

        self.assertEqual(response.status_code, 401)

    def test_given_failure_before_the_stream_when_posted_then_returns_500_with_name_only(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_record.side_effect = RuntimeError("mongodb://admin:secret@internal-host")

        with self.assertLogs("core.views.document_ai_view", level="ERROR"):
            response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions/stream")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})

    def test_given_failure_during_the_stream_when_posted_then_ends_with_error_name_only(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions()

        def broken_events(temp_file_id, prepared):
            yield {"type": "classification", "suggestion": prepared.suggestion}
            raise RuntimeError("mongodb://admin:secret@internal-host")

        with (
            mock.patch("core.views.document_ai_view.stream_suggestion_events", broken_events),
            self.assertLogs("core.views.document_ai_view", level="ERROR"),
        ):
            response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions/stream")
            events = self._events(response)

        self.assertEqual(events[0]["type"], "classification")
        self.assertEqual(events[-1], {"type": "error", "error": "RuntimeError"})
