import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase, override_settings

from core.models import (
    Area,
    ConfidentialityLevel,
    Discipline,
    Document,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    User,
)
from core.services import document_creation_service as service
from core.services.document_exceptions import (
    DocumentCodeCollisionError,
    DocumentStorageError,
    DocumentValidationError,
    DuplicateDocumentFileError,
    TempFileNotFoundError,
)

PDF_BYTES = b"%PDF-1.4 test document body"
TEMP_FILE_ID = "11111111-2222-4333-8444-555555555555"


@mock.patch("core.services.document_creation_service.get_mongo_db")
class DocumentCreationServiceTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        self.settings_override = override_settings(
            TEMP_UPLOAD_DIR=self.temp_dir, DOCUMENT_STORAGE_DIR=self.storage_dir
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.other_area = Area.objects.create(acronym="QUA", name="Qualidade")
        Area.objects.create(acronym="OLD", name="Desativada", active=False)
        self.user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=self.area
        )
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.project.disciplines.add(self.discipline)
        self.unlinked_discipline = Discipline.objects.create(code="HID", name="Hidráulica")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")

    def _temp_file(self, temp_file_id=TEMP_FILE_ID, content=PDF_BYTES, extension="pdf"):
        path = Path(self.temp_dir) / f"{temp_file_id}.{extension}"
        path.write_bytes(content)
        return path

    def _payload(self, **overrides):
        payload = {
            "temp_file_id": TEMP_FILE_ID,
            "title": "Desenho da caverna 14",
            "description": "Conjunto soldado",
            "project_id": self.project.id,
            "discipline_id": self.discipline.id,
            "document_type": "DWG",
            "confidentiality": "CONFIDENTIAL",
            "responsible_id": self.user.id,
            "areas": ["EST", "QUA"],
        }
        payload.update(overrides)
        return payload

    def test_should_reject_empty_payload_with_one_message_per_required_field(self, mongo):
        payload = {}

        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(payload)

        errors = context.exception.errors
        self.assertEqual(
            set(errors),
            {
                "title",
                "project_id",
                "discipline_id",
                "document_type",
                "confidentiality",
                "responsible_id",
                "areas",
                "temp_file_id",
            },
        )
        for field, error in errors.items():
            with self.subTest(field=field):
                self.assertEqual(set(error), {"code", "message"})
                self.assertEqual(error["code"], "invalid" if field == "areas" else "required")
                self.assertTrue(error["message"])

    def test_should_reject_non_object_payload(self, mongo):
        payload = ["not", "a", "dict"]

        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(payload)
        self.assertEqual(context.exception.errors["payload"]["code"], "invalid")

    def test_should_reject_title_and_description_over_the_limits(self, mongo):
        payload = self._payload(title="x" * 256, description="y" * 501)

        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(payload)

        errors = context.exception.errors
        self.assertEqual(errors["title"]["code"], "too_long")
        self.assertIn("at most 255", errors["title"]["message"])
        self.assertEqual(errors["description"]["code"], "too_long")
        self.assertIn("at most 500", errors["description"]["message"])

    def test_should_reject_unknown_or_inactive_catalog_entries(self, mongo):
        Project.objects.create(code="OLD", name="Encerrado", active=False)
        inactive_project = Project.objects.get(code="OLD")
        payload = self._payload(
            project_id=inactive_project.id,
            discipline_id=9999,
            document_type="XXX",
            responsible_id=9999,
            areas=["EST", "OLD", "NOPE"],
        )

        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(payload)

        errors = context.exception.errors
        for field in ("project_id", "discipline_id", "document_type", "responsible_id", "areas"):
            with self.subTest(field=field):
                self.assertEqual(errors[field]["code"], "not_found")
        self.assertEqual(errors["project_id"]["message"], "Project not found or inactive.")
        self.assertIn("['NOPE', 'OLD']", errors["areas"]["message"])

    def test_should_reject_discipline_outside_the_project(self, mongo):
        payload = self._payload(discipline_id=self.unlinked_discipline.id)

        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(payload)

        self.assertEqual(
            context.exception.errors["discipline_id"],
            {
                "code": "not_in_project",
                "message": "Discipline is not part of the selected project.",
            },
        )

    def test_should_reject_invalid_confidentiality_areas_and_temp_file_id(self, mongo):
        payload = self._payload(confidentiality="INTERNAL", areas="EST", temp_file_id="abc")

        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(payload)

        errors = context.exception.errors
        self.assertEqual(errors["confidentiality"]["code"], "invalid_choice")
        self.assertIn("must be one of", errors["confidentiality"]["message"])
        self.assertEqual(errors["areas"]["code"], "invalid")
        self.assertEqual(errors["temp_file_id"]["code"], "invalid")

    def test_should_require_at_least_one_area(self, mongo):
        payload = self._payload(areas=[])

        with self.assertRaises(DocumentValidationError) as context:
            service.validate_payload(payload)
        self.assertEqual(
            context.exception.errors["areas"],
            {"code": "required", "message": "At least one area is required."},
        )

    def test_should_accept_numeric_strings_and_normalize_codes(self, mongo):
        payload = self._payload(
            project_id=str(self.project.id),
            discipline_id=str(self.discipline.id),
            responsible_id=str(self.user.id),
            document_type=" dwg ",
            confidentiality="public",
            areas=[" est ", "qua", "EST"],
            title="  Título  ",
        )

        cleaned = service.validate_payload(payload)

        self.assertEqual(cleaned["project"], self.project)
        self.assertEqual(cleaned["document_type"], self.document_type)
        self.assertEqual(cleaned["confidentiality"], ConfidentialityLevel.PUBLIC)
        self.assertEqual({area.acronym for area in cleaned["areas"]}, {"EST", "QUA"})
        self.assertEqual(cleaned["title"], "Título")

    def test_should_describe_the_temp_file_using_mongo_metadata(self, mongo):
        self._temp_file()
        mongo.return_value.__getitem__.return_value.find_one.return_value = {
            "original_name": "caverna-14.pdf",
            "inferred_type": "application/pdf",
        }

        info = service.resolve_temp_file(TEMP_FILE_ID)

        self.assertEqual(info["original_name"], "caverna-14.pdf")
        self.assertEqual(info["extension"], "pdf")
        self.assertEqual(info["mime_type"], "application/pdf")
        self.assertEqual(info["size_bytes"], len(PDF_BYTES))
        self.assertEqual(len(info["sha256"]), 64)

    def test_should_fall_back_to_file_name_when_mongo_has_no_record(self, mongo):
        self._temp_file()
        mongo.return_value.__getitem__.return_value.find_one.return_value = None

        info = service.resolve_temp_file(TEMP_FILE_ID)

        self.assertEqual(info["original_name"], f"{TEMP_FILE_ID}.pdf")
        self.assertEqual(info["mime_type"], "application/pdf")

    def test_should_raise_when_temp_file_is_missing(self, mongo):

        with self.assertRaises(TempFileNotFoundError):
            service.resolve_temp_file(TEMP_FILE_ID)

    def test_should_raise_when_temp_file_has_an_unsupported_extension(self, mongo):
        self._temp_file(extension="exe")

        with self.assertRaises(TempFileNotFoundError):
            service.resolve_temp_file(TEMP_FILE_ID)

    def test_should_create_document_revision_file_and_areas_and_move_the_file(self, mongo):
        temp_path = self._temp_file()
        mongo.return_value.__getitem__.return_value.find_one.return_value = {
            "original_name": "caverna-14.pdf",
            "inferred_type": "application/pdf",
        }

        document = service.create_document(self._payload())

        self.assertEqual(document.code, "AK-2100-EST-DWG-0001")
        self.assertEqual(document.confidentiality_level, ConfidentialityLevel.CONFIDENTIAL)
        self.assertEqual(document.responsible, self.user)
        self.assertEqual({area.acronym for area in document.areas.all()}, {"EST", "QUA"})

        revision = Revision.objects.get(document=document)
        self.assertEqual(revision.version, 1)
        self.assertEqual(revision.status, RevisionStatus.PENDING)
        self.assertEqual(revision.author, self.user)
        self.assertIsNotNone(revision.issue_date)

        stored = File.objects.get(revision=revision)
        self.assertEqual(stored.original_name, "caverna-14.pdf")
        self.assertEqual(stored.extension, "pdf")
        self.assertEqual(stored.size_bytes, len(PDF_BYTES))
        self.assertEqual(
            stored.storage_path, "documents/AK-2100-EST-DWG-0001/v1/ak-2100-est-dwg-0001.pdf"
        )
        self.assertFalse(temp_path.exists())
        self.assertEqual((Path(self.storage_dir) / stored.storage_path).read_bytes(), PDF_BYTES)
        mongo.return_value.__getitem__.return_value.delete_one.assert_called_once_with(
            {"temp_file_id": TEMP_FILE_ID}
        )

    def test_should_increment_the_sequence_for_the_same_prefix(self, mongo):
        self._temp_file()
        service.create_document(self._payload())
        second_id = "22222222-2222-4333-8444-555555555555"
        self._temp_file(temp_file_id=second_id, content=b"%PDF-1.4 another body")

        document = service.create_document(self._payload(temp_file_id=second_id))

        self.assertEqual(document.code, "AK-2100-EST-DWG-0002")

    def test_should_retry_with_the_next_sequence_when_the_code_collides(self, mongo):
        self._temp_file()
        original_create = Document.objects.create
        calls = []

        def create_with_collision(**kwargs):
            calls.append(kwargs["code"])
            if len(calls) == 1:
                raise IntegrityError(
                    'duplicate key value violates unique constraint "document_code_key"'
                )
            return original_create(**kwargs)

        with mock.patch.object(Document.objects, "create", side_effect=create_with_collision):
            document = service.create_document(self._payload())

        self.assertEqual(calls, ["AK-2100-EST-DWG-0001", "AK-2100-EST-DWG-0001"])
        self.assertEqual(document.code, "AK-2100-EST-DWG-0001")
        self.assertEqual(Document.objects.count(), 1)

    def test_should_give_up_after_repeated_collisions(self, mongo):
        self._temp_file()
        always_collide = IntegrityError('unique constraint "document_code_key"')

        with (
            mock.patch.object(Document.objects, "create", side_effect=always_collide),
            self.assertRaises(DocumentCodeCollisionError),
        ):
            service.create_document(self._payload())
        self.assertEqual(Document.objects.count(), 0)

    def test_should_reject_a_file_already_attached_to_a_document(self, mongo):
        self._temp_file()
        service.create_document(self._payload())
        duplicate_id = "33333333-2222-4333-8444-555555555555"
        self._temp_file(temp_file_id=duplicate_id, content=PDF_BYTES)

        with self.assertRaises(DuplicateDocumentFileError) as context:
            service.create_document(self._payload(temp_file_id=duplicate_id))
        self.assertEqual(context.exception.document.code, "AK-2100-EST-DWG-0001")
        self.assertEqual(Document.objects.count(), 1)

    def test_should_roll_back_everything_when_the_file_cannot_be_moved(self, mongo):
        temp_path = self._temp_file()

        with (
            mock.patch("core.services.document_creation_service.shutil.move", side_effect=OSError),
            self.assertRaises(DocumentStorageError),
        ):
            service.create_document(self._payload())

        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(Revision.objects.count(), 0)
        self.assertEqual(File.objects.count(), 0)
        self.assertTrue(temp_path.exists())
        mongo.return_value.__getitem__.return_value.delete_one.assert_not_called()

    def test_should_not_touch_the_file_when_validation_fails(self, mongo):
        temp_path = self._temp_file()

        with self.assertRaises(DocumentValidationError):
            service.create_document(self._payload(title=""))
        self.assertTrue(temp_path.exists())
        self.assertEqual(Document.objects.count(), 0)
