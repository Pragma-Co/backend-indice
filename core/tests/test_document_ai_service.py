import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import Client, TestCase, override_settings

from classifier.persistence import ArtifactsError
from classifier.prediction import Prediction
from core.models import Area, Discipline, DocumentType
from core.services.document_ai_exceptions import UnsupportedFileTypeError
from core.services.document_ai_service import suggest_document_metadata
from core.services.document_exceptions import TempFileNotFoundError

TEMP_FILE_ID = "11111111-2222-4333-8444-555555555555"

NULL_SUGGESTION = {
    "title": None,
    "description": None,
    "project": None,
    "discipline": None,
    "document_type": None,
    "area": None,
}


def predictions(discipline="MECHANICAL", document_type="SPECIFICATION", area="DESIGN"):
    return {
        "discipline": Prediction(discipline, 0.9),
        "document_type": Prediction(document_type, 0.8),
        "area": Prediction(area, 0.7),
    }


@mock.patch("core.services.document_ai_service.get_mongo_db")
@mock.patch(
    "core.services.document_ai_service.get_temp_upload_record",
    return_value={"extracted_text": "texto processado"},
)
@mock.patch("core.services.document_ai_service.get_classifier")
class SuggestDocumentMetadataTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.settings_override = override_settings(TEMP_UPLOAD_DIR=self.temp_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="ESP", name="Especificação Técnica")
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")

    def _temp_file(self, extension="pdf"):
        path = Path(self.temp_dir) / f"{TEMP_FILE_ID}.{extension}"
        path.write_bytes(b"conteudo")
        return path

    def test_given_valid_pdf_when_suggested_then_maps_labels_to_catalog_items(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions()

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(result["discipline"], {"id": self.discipline.id, "name": "Estruturas"})
        self.assertEqual(
            result["document_type"], {"id": self.document_type.id, "name": "Especificação Técnica"}
        )
        self.assertEqual(result["area"], {"id": self.area.id, "name": "Engenharia Estrutural"})
        self.assertIsNone(result["title"])
        self.assertIsNone(result["description"])
        self.assertIsNone(result["project"])

    def test_given_valid_pdf_when_suggested_then_classifies_the_extracted_text_once(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions()

        suggest_document_metadata(TEMP_FILE_ID)

        mock_classifier.return_value.predict.assert_called_once_with("texto processado")

    def test_given_label_without_catalog_item_when_suggested_then_returns_label_with_null_id(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions(
            discipline="ELECTRICAL", document_type="HANDBOOK", area="OTHER_STAGE"
        )

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(result["discipline"], {"id": None, "name": "ELECTRICAL"})
        self.assertEqual(result["document_type"], {"id": None, "name": "HANDBOOK"})
        self.assertEqual(result["area"], {"id": None, "name": "OTHER_STAGE"})

    def test_given_valid_pdf_when_suggested_then_saves_suggestion_to_temp_upload_record(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions()

        result = suggest_document_metadata(TEMP_FILE_ID)

        mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once_with(
            {"temp_file_id": TEMP_FILE_ID}, {"$set": {"ai_suggestion": result}}
        )

    def test_given_missing_temp_file_when_suggested_then_raises_temp_file_not_found_error(
        self, mock_classifier, mock_record, mock_mongo
    ):
        with self.assertRaises(TempFileNotFoundError):
            suggest_document_metadata(TEMP_FILE_ID)
        mock_classifier.assert_not_called()
        mock_mongo.assert_not_called()

    def test_given_unsupported_extension_when_suggested_then_raises_unsupported_file_type_error(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file(extension="png")

        with self.assertRaises(UnsupportedFileTypeError):
            suggest_document_metadata(TEMP_FILE_ID)
        mock_classifier.assert_not_called()
        mock_mongo.assert_not_called()

    def test_given_classifier_failure_when_suggested_then_saves_and_returns_null_fields(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        failures = {
            "artifacts": ArtifactsError("model.pt not found"),
            "generic": RuntimeError("boom"),
        }
        for failure_name, error in failures.items():
            with self.subTest(failure=failure_name):
                mock_classifier.return_value.predict.side_effect = error
                mock_mongo.reset_mock()

                with self.assertLogs("core.services.document_ai_service", level="ERROR"):
                    result = suggest_document_metadata(TEMP_FILE_ID)

                self.assertEqual(result, NULL_SUGGESTION)
                mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once_with(
                    {"temp_file_id": TEMP_FILE_ID}, {"$set": {"ai_suggestion": result}}
                )

    def test_given_no_extracted_text_when_suggested_then_skips_classifier_and_saves_null_fields(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        for extracted_text in (None, "", "   \n\t"):
            with self.subTest(extracted_text=extracted_text):
                mock_record.return_value = {"extracted_text": extracted_text}
                mock_mongo.reset_mock()

                result = suggest_document_metadata(TEMP_FILE_ID)

                self.assertEqual(result, NULL_SUGGESTION)
                mock_classifier.return_value.predict.assert_not_called()
                mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once_with(
                    {"temp_file_id": TEMP_FILE_ID}, {"$set": {"ai_suggestion": result}}
                )

    def test_given_mongo_write_fails_when_suggested_then_response_is_not_blocked(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions()
        mock_mongo.return_value.__getitem__.return_value.update_one.side_effect = Exception("boom")

        result = suggest_document_metadata(TEMP_FILE_ID)

        self.assertEqual(result["discipline"]["name"], "Estruturas")


@mock.patch("core.services.document_ai_service.get_mongo_db")
@mock.patch(
    "core.services.document_ai_service.get_temp_upload_record",
    return_value={"extracted_text": "texto processado"},
)
@mock.patch("core.services.document_ai_service.get_classifier")
class SuggestDocumentMetadataViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.settings_override = override_settings(TEMP_UPLOAD_DIR=self.temp_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        Discipline.objects.create(code="EST", name="Estruturas")
        DocumentType.objects.create(code="ESP", name="Especificação Técnica")
        Area.objects.create(acronym="EST", name="Engenharia Estrutural")

    def _temp_file(self, extension="pdf"):
        path = Path(self.temp_dir) / f"{TEMP_FILE_ID}.{extension}"
        path.write_bytes(b"conteudo")
        return path

    def test_given_valid_pdf_when_posted_then_returns_200_with_expected_shape(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.return_value = predictions()

        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), set(NULL_SUGGESTION))
        self.assertEqual(body["discipline"]["name"], "Estruturas")
        self.assertEqual(body["document_type"]["name"], "Especificação Técnica")
        self.assertEqual(body["area"]["name"], "Engenharia Estrutural")
        self.assertIsNone(body["title"])
        mock_mongo.return_value.__getitem__.return_value.update_one.assert_called_once()

    def test_given_missing_temp_file_when_posted_then_returns_404(
        self, mock_classifier, mock_record, mock_mongo
    ):
        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")
        self.assertEqual(response.status_code, 404)

    def test_given_unsupported_extension_when_posted_then_returns_422(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file(extension="png")

        response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")
        self.assertEqual(response.status_code, 422)

    def test_given_get_request_when_called_then_returns_405(
        self, mock_classifier, mock_record, mock_mongo
    ):
        response = self.client.get(f"/documents/{TEMP_FILE_ID}/suggestions")
        self.assertEqual(response.status_code, 405)

    def test_given_classifier_failure_when_posted_then_returns_200_with_null_suggestion_fields(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_classifier.return_value.predict.side_effect = Exception("boom")

        with self.assertLogs("core.services.document_ai_service", level="ERROR"):
            response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), NULL_SUGGESTION)

    def test_given_unexpected_error_when_posted_then_returns_500_with_exception_name_only(
        self, mock_classifier, mock_record, mock_mongo
    ):
        self._temp_file()
        mock_record.side_effect = RuntimeError("mongodb://admin:secret@internal-host")

        with self.assertLogs("core.views.document_ai_view", level="ERROR"):
            response = self.client.post(f"/documents/{TEMP_FILE_ID}/suggestions")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})
