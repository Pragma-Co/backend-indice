import json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from core.ollama_client import stream_ollama


def fake_stream(payloads):
    response = mock.MagicMock()
    response.__enter__.return_value = [
        json.dumps(payload).encode("utf-8") + b"\n" for payload in payloads
    ]
    return response


def chunk(content, done=False):
    return {"message": {"role": "assistant", "content": content}, "done": done}


@override_settings(
    OLLAMA_BASE_URL="http://ollama.test:11434/", OLLAMA_MODEL="llama3.2", OLLAMA_TIMEOUT=3
)
@mock.patch("core.ollama_client.urlopen")
class StreamOllamaTests(SimpleTestCase):
    def test_given_streamed_answer_when_iterated_then_yields_each_piece_in_order(
        self, mock_urlopen
    ):
        mock_urlopen.return_value = fake_stream([chunk('{"title": "Mem'), chunk('orial"}')])

        result = list(stream_ollama("system", "user"))

        self.assertEqual(result, ['{"title": "Mem', 'orial"}'])

    def test_given_done_marker_when_iterated_then_stops_and_skips_empty_pieces(self, mock_urlopen):
        mock_urlopen.return_value = fake_stream(
            [chunk("a"), chunk("", done=True), chunk("after the end")]
        )

        result = list(stream_ollama("system", "user"))

        self.assertEqual(result, ["a"])

    def test_given_request_when_started_then_asks_ollama_to_stream_with_the_format(
        self, mock_urlopen
    ):
        mock_urlopen.return_value = fake_stream([chunk("a", done=True)])
        response_format = {"type": "object"}

        list(stream_ollama("system", "user", temperature=0.4, response_format=response_format))

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "http://ollama.test:11434/api/chat")
        self.assertEqual(mock_urlopen.call_args.kwargs, {"timeout": 3})
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["format"], response_format)
        self.assertEqual(payload["options"], {"temperature": 0.4})

    def test_given_error_line_when_iterated_then_raises_value_error(self, mock_urlopen):
        mock_urlopen.return_value = fake_stream([chunk("a"), {"error": "model not found"}])

        with self.assertRaises(ValueError):
            list(stream_ollama("system", "user"))
