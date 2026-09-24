import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import httpx
from django.test import Client, TestCase, override_settings
from groq import APIConnectionError, APITimeoutError, RateLimitError

from core.models import Area, Discipline, DocumentType, Project
from core.services.document_ai_exceptions import UnsupportedFileTypeError
from core.services.document_ai_service import suggest_document_metadata
from core.services.document_exceptions import TempFileNotFoundError

TEMP_FILE_ID = "11111111-2222-4333-8444-555555555555"

GROQ_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

NULL_SUGGESTION = {
    "title": None,
    "description": None,
    "project": None,
    "discipline": None,
    "document_type": None,
    "area": None,
}


def _fake_groq_response(content: str):
    response = mock.Mock()
    response.choices = [mock.Mock(message=mock.Mock(content=content))]
    return response


def _happy_path_answer():
    return _fake_groq_response(
        json.dumps(
            {
                "title": "Relatório de fadiga estrutural",
                "description": "Descrição breve do documento.",
                "project": "Fuselagem",
                "discipline": "Estruturas",
                "document_type": "Desenho Técnico",
                "area": "Engenharia Estrutural",
            }
        )
    )


@mock.patch("core.services.document_ai_service.get_mongo_db")
@mock.patch(
    "core.services.document_ai_service.get_temp_upload_record",
    return_value={"extracted_text": "texto processado"},
)
@mock.patch("core.services.document_ai_service.get_groq_client")
class SuggestDocumentMetadataTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.settings_override = override_settings(TEMP_UPLOAD_DIR=self.temp_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.other_discipline = Discipline.objects.create(code="HID", name="Hidráulica")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho Técnico")
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.project.disciplines.add(self.discipline)

    def _temp_file(self, extension="pdf"):
        path = Path(self.temp_dir) / f"{TEMP_FILE_ID}.{extension}"
        path.write_bytes(b"conteudo")
        return path

    def test_given_valid_pdf_when_suggested_then_returns_matched_fields(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _happy_path_answer()

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(result["title"], "Relatório de fadiga estrutural")
        self.assertEqual(result["description"], "Descrição breve do documento.")
        self.assertEqual(result["project"], {"id": self.project.id, "name": "Fuselagem"})
        self.assertEqual(result["discipline"], {"id": self.discipline.id, "name": "Estruturas"})
        self.assertEqual(
            result["document_type"], {"id": self.document_type.id, "name": "Desenho Técnico"}
        )
        self.assertEqual(result["area"], {"id": self.area.id, "name": "Engenharia Estrutural"})

    def test_given_valid_pdf_when_suggested_then_asks_groq_only_once(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _happy_path_answer()

        suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(mock_client.return_value.chat.completions.create.call_count, 1)

    def test_given_discipline_outside_matched_project_when_suggested_then_returns_null_id(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _fake_groq_response(
            json.dumps(
                {
                    "title": "T",
                    "description": "D",
                    "project": "Fuselagem",
                    "discipline": "Hidráulica",
                    "document_type": "Desenho Técnico",
                    "area": "Engenharia Estrutural",
                }
            )
        )

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertIsNone(result["discipline"]["id"])
        self.assertEqual(result["discipline"]["name"], "Hidráulica")

    def test_given_valid_pdf_when_suggested_then_saves_suggestion_to_temp_upload_record(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _happy_path_answer()

        result = suggest_document_metadata(TEMP_FILE_ID)

        mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once_with(
            {"temp_file_id": TEMP_FILE_ID}, {"$set": {"ai_suggestion": result}}
        )

    def test_given_unrecognized_suggestion_when_matched_then_returns_null_id(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _fake_groq_response(
            json.dumps(
                {
                    "title": "T",
                    "description": "D",
                    "project": "Projeto Desconhecido",
                    "discipline": "Disciplina Desconhecida",
                    "document_type": "Tipo Desconhecido",
                    "area": "Área Desconhecida",
                }
            )
        )

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertIsNone(result["project"]["id"])
        self.assertIsNone(result["discipline"]["id"])
        self.assertIsNone(result["document_type"]["id"])
        self.assertIsNone(result["area"]["id"])

    def test_given_answer_wrapped_in_extra_text_when_parsed_then_extracts_json_block(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        payload = {
            "title": "T",
            "description": "D",
            "project": "Fuselagem",
            "discipline": "Estruturas",
            "document_type": "Desenho Técnico",
            "area": "Engenharia Estrutural",
        }
        mock_client.return_value.chat.completions.create.return_value = _fake_groq_response(
            f"Aqui está o resultado:\n{json.dumps(payload)}\nFim."
        )

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(result["title"], "T")

    def test_given_answer_is_not_valid_json_when_suggested_then_returns_null_fields(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _fake_groq_response(
            "isto não é um JSON válido"
        )

        with self.assertLogs("core.services.document_ai_service", level="ERROR"):
            result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(result, NULL_SUGGESTION)

    def test_given_answer_with_missing_or_blank_fields_when_suggested_then_those_fields_are_null(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _fake_groq_response(
            json.dumps({"title": "  ", "project": "Fuselagem", "area": ""})
        )

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(
            result,
            {
                **NULL_SUGGESTION,
                "project": {"id": self.project.id, "name": "Fuselagem"},
            },
        )

    def test_given_missing_temp_file_when_suggested_then_raises_temp_file_not_found_error(
        self, mock_client, mock_record, mock_mongo
    ):
        with self.assertRaises(TempFileNotFoundError):
            suggest_document_metadata(TEMP_FILE_ID)
        mock_client.assert_not_called()
        mock_mongo.assert_not_called()

    def test_given_unsupported_extension_when_suggested_then_raises_unsupported_file_type_error(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file(extension="png")

        with self.assertRaises(UnsupportedFileTypeError):
            suggest_document_metadata(TEMP_FILE_ID)
        mock_client.assert_not_called()
        mock_mongo.assert_not_called()

    def test_given_groq_failure_when_suggested_then_saves_and_returns_null_fields(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        rate_limit_response = httpx.Response(status_code=429, request=GROQ_REQUEST)
        failures = {
            "generic": (Exception("boom"), "ERROR"),
            "timeout": (APITimeoutError(request=GROQ_REQUEST), "WARNING"),
            "rate_limit": (
                RateLimitError("rate limited", response=rate_limit_response, body=None),
                "WARNING",
            ),
            "connection": (APIConnectionError(request=GROQ_REQUEST), "WARNING"),
        }
        for failure_name, (error, log_level) in failures.items():
            with self.subTest(failure=failure_name):
                mock_client.return_value.chat.completions.create.side_effect = error
                mock_mongo.reset_mock()

                with self.assertLogs("core.services.document_ai_service", level=log_level):
                    result = suggest_document_metadata(TEMP_FILE_ID)

                self.assertEqual(result, NULL_SUGGESTION)
                mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once_with(
                    {"temp_file_id": TEMP_FILE_ID}, {"$set": {"ai_suggestion": result}}
                )

    def test_given_no_extracted_text_when_suggested_then_skips_ai_and_saves_null_fields(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        for extracted_text in (None, "", "   \n\t"):
            with self.subTest(extracted_text=extracted_text):
                mock_record.return_value = {"extracted_text": extracted_text}
                mock_mongo.reset_mock()

                result = suggest_document_metadata(TEMP_FILE_ID)

                self.assertEqual(result, NULL_SUGGESTION)
                mock_client.return_value.chat.completions.create.assert_not_called()
                mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once_with(
                    {"temp_file_id": TEMP_FILE_ID}, {"$set": {"ai_suggestion": result}}
                )

    def test_given_mongo_write_fails_when_suggested_then_response_is_not_blocked(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _happy_path_answer()
        mock_mongo.return_value.__getitem__.return_value.update_one.side_effect = Exception("boom")

        result = suggest_document_metadata(TEMP_FILE_ID)  # should not raise

        self.assertEqual(result["description"], "Descrição breve do documento.")


@mock.patch("core.services.document_ai_service.get_mongo_db")
@mock.patch(
    "core.services.document_ai_service.get_temp_upload_record",
    return_value={"extracted_text": "texto processado"},
)
@mock.patch("core.services.document_ai_service.get_groq_client")
class SuggestDocumentMetadataViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.settings_override = override_settings(TEMP_UPLOAD_DIR=self.temp_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        discipline = Discipline.objects.create(code="EST", name="Estruturas")
        DocumentType.objects.create(code="DWG", name="Desenho Técnico")
        Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        project = Project.objects.create(code="AK-2100", name="Fuselagem")
        project.disciplines.add(discipline)

    def _temp_file(self, extension="pdf"):
        path = Path(self.temp_dir) / f"{TEMP_FILE_ID}.{extension}"
        path.write_bytes(b"conteudo")
        return path

    def test_given_valid_pdf_when_posted_then_returns_200_with_expected_shape(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.return_value = _happy_path_answer()

        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["title"], "Relatório de fadiga estrutural")
        self.assertEqual(body["project"]["name"], "Fuselagem")
        self.assertEqual(body["discipline"]["name"], "Estruturas")
        self.assertEqual(body["document_type"]["name"], "Desenho Técnico")
        self.assertEqual(body["area"]["name"], "Engenharia Estrutural")
        self.assertEqual(body["description"], "Descrição breve do documento.")
        mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once()

    def test_given_missing_temp_file_when_posted_then_returns_404(
        self, mock_client, mock_record, mock_mongo
    ):
        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")
        self.assertEqual(response.status_code, 404)

    def test_given_unsupported_extension_when_posted_then_returns_422(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file(extension="png")

        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")
        self.assertEqual(response.status_code, 422)

    def test_given_get_request_when_called_then_returns_405(
        self, mock_client, mock_record, mock_mongo
    ):
        response = self.client.get(f"/documents/{TEMP_FILE_ID}/suggestions")
        self.assertEqual(response.status_code, 405)

    def test_given_groq_failure_when_posted_then_returns_200_with_null_suggestion_fields(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_client.return_value.chat.completions.create.side_effect = Exception("boom")

        with self.assertLogs("core.services.document_ai_service", level="ERROR"):
            response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), NULL_SUGGESTION)

    def test_given_unexpected_error_when_posted_then_returns_500_with_exception_name_only(
        self, mock_client, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_record.side_effect = RuntimeError("mongodb://admin:secret@internal-host")

        with self.assertLogs("core.views.document_ai_view", level="ERROR"):
            response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})
