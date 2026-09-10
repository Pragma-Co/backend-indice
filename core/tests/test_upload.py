import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from core.services.file_validation_service import (
    format_file_size,
    sniff_file_type,
    validate_file_size,
    validate_file_type,
)
from core.services.upload_exceptions import (
    FileTooLargeError,
    InvalidFileTypeError,
    MissingFileError,
)
from core.services.temp_upload_service import store_uploaded_file

PDF_HEADER = b"%PDF-1.4 fake pdf body"
PNG_HEADER = b"\x89PNG\r\n\x1a\n fake png body"
JPEG_HEADER = b"\xff\xd8\xff fake jpeg body"
DOC_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 fake doc body"
INVALID_HEADER = b"this is a plain text file, not a real document"


class FormatFileSizeTests(TestCase):
    def test_given_bytes_under_1kb_when_formatted_then_shown_in_bytes(self):
        result = format_file_size(500)
        self.assertEqual(result, "500 B")

    def test_given_bytes_in_kb_range_when_formatted_then_shown_in_kb(self):
        result = format_file_size(1536)
        self.assertEqual(result, "1.5 KB")

    def test_given_bytes_in_mb_range_when_formatted_then_shown_in_mb(self):
        result = format_file_size(1536000)
        self.assertEqual(result, "1.5 MB")


class SniffFileTypeTests(TestCase):
    def test_given_pdf_header_when_sniffed_then_returns_pdf_type(self):
        uploaded = SimpleUploadedFile("file.pdf", PDF_HEADER)
        file_type = sniff_file_type(uploaded)
        self.assertIsNotNone(file_type)
        self.assertEqual(file_type.mime_type, "application/pdf")

    def test_given_png_header_when_sniffed_then_returns_png_type(self):
        uploaded = SimpleUploadedFile("file.png", PNG_HEADER)
        file_type = sniff_file_type(uploaded)
        self.assertEqual(file_type.mime_type, "image/png")

    def test_given_jpeg_header_when_sniffed_then_returns_jpeg_type(self):
        uploaded = SimpleUploadedFile("file.jpg", JPEG_HEADER)
        file_type = sniff_file_type(uploaded)
        self.assertEqual(file_type.mime_type, "image/jpeg")

    def test_given_doc_header_when_sniffed_then_returns_doc_type(self):
        uploaded = SimpleUploadedFile("file.doc", DOC_HEADER)
        file_type = sniff_file_type(uploaded)
        self.assertEqual(file_type.mime_type, "application/msword")

    def test_given_disguised_file_when_sniffed_then_returns_none(self):
        uploaded = SimpleUploadedFile("file.pdf", INVALID_HEADER)
        file_type = sniff_file_type(uploaded)
        self.assertIsNone(file_type)

    def test_given_disguised_file_when_validated_then_raises_invalid_file_type_error(self):
        uploaded = SimpleUploadedFile("file.pdf", INVALID_HEADER)
        with self.assertRaises(InvalidFileTypeError):
            validate_file_type(uploaded)


class ValidateFileSizeTests(TestCase):
    @override_settings(MAX_UPLOAD_SIZE_BYTES=1024)
    def test_given_file_under_limit_when_validated_then_no_error_is_raised(self):
        uploaded = SimpleUploadedFile("file.pdf", b"x" * 100)
        validate_file_size(uploaded)  # should not raise

    @override_settings(MAX_UPLOAD_SIZE_BYTES=1024)
    def test_given_file_over_limit_when_validated_then_raises_file_too_large_error(self):
        uploaded = SimpleUploadedFile("file.pdf", b"x" * 2048)
        with self.assertRaises(FileTooLargeError):
            validate_file_size(uploaded)


class StoreUploadedFileTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    @override_settings()
    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_given_no_file_when_stored_then_raises_missing_file_error(self, mock_mongo):
        with self.assertRaises(MissingFileError):
            store_uploaded_file(None)
        mock_mongo.assert_not_called()

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_given_valid_pdf_when_stored_then_returns_expected_metadata(self, mock_mongo):
        with override_settings(TEMP_UPLOAD_DIR=self.temp_dir, MAX_UPLOAD_SIZE_BYTES=1024 * 1024):
            uploaded = SimpleUploadedFile("relatorio.pdf", PDF_HEADER)
            result = store_uploaded_file(uploaded)

        self.assertIn("temp_file_id", result)
        self.assertEqual(result["original_name"], "relatorio.pdf")
        self.assertEqual(result["inferred_type"], "application/pdf")
        mock_mongo.return_value.__getitem__.return_value.insert_one.assert_called_once()

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_given_valid_file_when_stored_then_file_is_written_to_temp_dir(self, mock_mongo):
        with override_settings(TEMP_UPLOAD_DIR=self.temp_dir, MAX_UPLOAD_SIZE_BYTES=1024 * 1024):
            uploaded = SimpleUploadedFile("relatorio.pdf", PDF_HEADER)
            result = store_uploaded_file(uploaded)

        expected_path = f"{self.temp_dir}/{result['temp_file_id']}.pdf"
        with open(expected_path, "rb") as saved_file:
            self.assertEqual(saved_file.read(), PDF_HEADER)

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_given_mongo_write_fails_when_stored_then_response_is_not_blocked(self, mock_mongo):
        mock_mongo.return_value.__getitem__.return_value.insert_one.side_effect = Exception("boom")
        with override_settings(TEMP_UPLOAD_DIR=self.temp_dir, MAX_UPLOAD_SIZE_BYTES=1024 * 1024):
            uploaded = SimpleUploadedFile("relatorio.pdf", PDF_HEADER)
            result = store_uploaded_file(uploaded)  # should not raise

        self.assertIn("temp_file_id", result)


class UploadDocumentViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    @mock.patch("core.services.temp_upload_service.get_mongo_db")
    def test_given_valid_pdf_when_posted_then_returns_201_with_expected_shape(self, mock_mongo):
        uploaded = SimpleUploadedFile("relatorio.pdf", PDF_HEADER)
        with override_settings(TEMP_UPLOAD_DIR=self.temp_dir, MAX_UPLOAD_SIZE_BYTES=1024 * 1024):
            response = self.client.post("/documents/upload", {"file": uploaded})

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("temp_file_id", body)
        self.assertEqual(body["original_name"], "relatorio.pdf")
        self.assertEqual(body["inferred_type"], "application/pdf")

    def test_given_no_file_when_posted_then_returns_400(self):
        response = self.client.post("/documents/upload", {})
        self.assertEqual(response.status_code, 400)

    def test_given_disguised_file_when_posted_then_returns_400(self):
        uploaded = SimpleUploadedFile("fake.pdf", INVALID_HEADER)
        response = self.client.post("/documents/upload", {"file": uploaded})
        self.assertEqual(response.status_code, 400)

    def test_given_file_over_limit_when_posted_then_returns_413(self):
        uploaded = SimpleUploadedFile("big.pdf", PDF_HEADER + b"x" * 2048)
        with override_settings(MAX_UPLOAD_SIZE_BYTES=1024):
            response = self.client.post("/documents/upload", {"file": uploaded})
        self.assertEqual(response.status_code, 413)

    def test_given_get_request_when_called_then_returns_405(self):
        response = self.client.get("/documents/upload")
        self.assertEqual(response.status_code, 405)