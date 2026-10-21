import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from docx import Document as DocxDocument

from classifier.prediction import Prediction
from core.models import (
    AccessStatus,
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    Project,
    Revision,
    RevisionStatus,
    Role,
    User,
)
from core.services import document_creation_service
from core.services.manager_activity_exceptions import ActivityQueryError
from core.services.manager_activity_service import (
    ACCESS,
    FAILURE,
    INGESTION_FAILURE,
    MODERATION,
    REVISION,
    SUCCESS,
    UPLOAD,
    list_activities,
    parse_activity_query,
)

PDF_HEADER = b"%PDF-1.4 fake pdf body"
TEMP_FILE_ID = "11111111-2222-4333-8444-555555555555"


class ManagerActivityFixtureMixin:
    def setUp(self):
        self.now = timezone.now()
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.other_area = Area.objects.create(acronym="MFG", name="Manufatura e Montagem")
        self.manager = self._user("manager@example.com", "Manager", Role.AUDITOR, self.area)
        self.author = self._user("author@example.com", "Author", Role.AUTHOR, self.area)
        self.other_manager = self._user(
            "other.manager@example.com", "Other Manager", Role.AUDITOR, self.other_area
        )
        self.outsider = self._user("outsider@example.com", "Outsider", Role.AUTHOR, self.other_area)
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.document = self._document("AK-2100-EST-DWG-0001", self.area)
        self.revision = self._revision(self.document, 1)
        self.access = DocumentAccess.objects.create(
            document=self.document,
            user=self.outsider,
            status=AccessStatus.PENDING,
            justification="Preciso revisar a furação",
            requested_at=self.now,
        )
        self.other_document = self._document("AK-2100-MFG-DWG-0002", self.other_area)
        self.other_revision = self._revision(self.other_document, 1)
        self.client = Client()

    def _user(self, email, name, role, area):
        return User.objects.create_user(
            email=email, password="secret", name=name, role=role, area=area
        )

    def _document(self, code, area):
        document = Document.objects.create(
            code=code,
            title=f"Documento {code}",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            confidentiality_level="PUBLIC",
            responsible=self.author,
            created_by=self.author,
        )
        document.areas.add(area)
        return document

    def _revision(self, document, version):
        return Revision.objects.create(
            document=document,
            version=version,
            status=RevisionStatus.PENDING,
            change_description="Atualiza a furação da caverna 14",
            author=self.author,
        )

    def _entry(self, action, entity, entity_id=None, record=None, user=None, minutes_ago=0):
        return AuditLog.objects.create(
            user=user if user is not None else self.author,
            action=action,
            entity=entity,
            entity_id=entity_id,
            record=record,
            occurred_at=self.now - timedelta(minutes=minutes_ago),
        )

    def _upload_entry(self, extraction="SUCCESS", detail=None, user=None, minutes_ago=0):
        return self._entry(
            AuditAction.DOC_UPLOAD_SUCCESS,
            "temp_upload",
            record={
                "temp_file_id": TEMP_FILE_ID,
                "original_name": "caverna-14.pdf",
                "sha256": "a" * 64,
                "ingestion": {"extraction": extraction, "detail": detail},
            },
            user=user,
            minutes_ago=minutes_ago,
        )

    def _results(self, params=None, manager=None):
        return list_activities(manager or self.manager, params or {})["results"]


class ActivityScopeAndOrderTests(ManagerActivityFixtureMixin, TestCase):
    def test_should_list_only_events_of_the_managers_area_newest_first(self):
        self._entry(
            AuditAction.DOC_SUBMIT_SUCCESS,
            "document",
            self.document.pk,
            {"document_code": self.document.code, "version": 1},
            minutes_ago=30,
        )
        self._entry(
            AuditAction.DOC_REVISION_CREATED,
            "document",
            self.document.pk,
            {"document_code": self.document.code, "version": 2, "file_count": 1},
            minutes_ago=10,
        )
        self._upload_entry(minutes_ago=20)
        self._entry(
            AuditAction.DOC_SUBMIT_SUCCESS,
            "document",
            self.other_document.pk,
            {"document_code": self.other_document.code},
            minutes_ago=5,
        )
        self._upload_entry(user=self.outsider, minutes_ago=1)
        self._entry(AuditAction.LOGIN, "app_user", self.author.pk, minutes_ago=2)
        self._entry(
            AuditAction.UPDATE,
            "app_user",
            self.author.pk,
            {"event": "PERSONAL_DATA_UPDATED"},
            minutes_ago=3,
        )

        results = self._results()

        self.assertEqual(
            [item["event"] for item in results],
            ["REVISION_SUBMITTED", "FILE_UPLOADED", "DOCUMENT_REGISTERED"],
        )
        self.assertEqual([item["document"]["code"] for item in results[:1]], [self.document.code])
        timestamps = [item["timestamp"] for item in results]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_should_resolve_the_document_of_revision_and_access_events(self):
        self._entry(
            AuditAction.UPDATE,
            "revision",
            self.revision.pk,
            {"event": "REVISION_APPROVED", "version": 1, "justification": "Conforme"},
            user=self.manager,
        )
        self._entry(
            AuditAction.UPDATE,
            "document_access",
            self.access.pk,
            {"event": "ACCESS_REJECTED", "document_id": self.document.pk},
            user=self.manager,
        )
        self._entry(
            AuditAction.UPDATE,
            "revision",
            self.other_revision.pk,
            {"event": "REVISION_APPROVED", "version": 1},
            user=self.other_manager,
        )

        results = self._results()

        self.assertEqual(len(results), 2)
        self.assertEqual({item["document"]["id"] for item in results}, {self.document.pk})
        self.assertEqual({item["user"]["name"] for item in results}, {"Manager"})

    def test_should_show_the_other_managers_area_to_the_other_manager(self):
        self._entry(
            AuditAction.DOC_SUBMIT_SUCCESS,
            "document",
            self.other_document.pk,
            {"document_code": self.other_document.code},
        )

        mine = self._results()
        theirs = self._results(manager=self.other_manager)

        self.assertEqual(mine, [])
        self.assertEqual([item["document"]["code"] for item in theirs], [self.other_document.code])


class ActivityClassificationTests(ManagerActivityFixtureMixin, TestCase):
    def test_should_classify_each_kind_of_event(self):
        cases = {
            "upload": (self._upload_entry(), UPLOAD, SUCCESS, "FILE_UPLOADED"),
            "upload_without_text": (
                self._upload_entry("EMPTY", "No text found in the file."),
                UPLOAD,
                SUCCESS,
                "FILE_UPLOADED",
            ),
            "extraction_failure": (
                self._upload_entry("FAILURE", "Text extraction failed: PdfReadError."),
                INGESTION_FAILURE,
                FAILURE,
                "TEXT_EXTRACTION_FAILED",
            ),
            "legacy_upload": (
                self._entry(
                    AuditAction.DOC_UPLOAD_SUCCESS,
                    "temp_upload",
                    record={"temp_file_id": TEMP_FILE_ID, "original_name": "antigo.pdf"},
                ),
                UPLOAD,
                SUCCESS,
                "FILE_UPLOADED",
            ),
            "duplicate": (
                self._entry(
                    AuditAction.DOC_UPLOAD_DUPLICATE,
                    "document",
                    self.document.pk,
                    {
                        "stage": "upload",
                        "document_code": self.document.code,
                        "original_name": "x.pdf",
                    },
                ),
                UPLOAD,
                FAILURE,
                "DUPLICATE_FILE_REFUSED",
            ),
            "classification_done": (
                self._entry(
                    AuditAction.UPDATE,
                    "temp_upload",
                    record={"event": "AI_CLASSIFICATION", "status": "SUCCESS", "detail": None},
                ),
                UPLOAD,
                SUCCESS,
                "AI_CLASSIFICATION_DONE",
            ),
            "classification_failed": (
                self._entry(
                    AuditAction.UPDATE,
                    "temp_upload",
                    record={
                        "event": "AI_CLASSIFICATION",
                        "status": "FAILURE",
                        "detail": "AI classification failed: AISuggestionError.",
                    },
                ),
                INGESTION_FAILURE,
                FAILURE,
                "AI_CLASSIFICATION_FAILED",
            ),
            "content_indexed": (
                self._entry(
                    AuditAction.UPDATE,
                    "document",
                    self.document.pk,
                    {
                        "event": "CONTENT_INDEXED",
                        "status": "SUCCESS",
                        "detail": "Content indexed: 120 characters, 2 thematic tags.",
                        "document_code": self.document.code,
                        "version": 1,
                    },
                ),
                UPLOAD,
                SUCCESS,
                "CONTENT_INDEXED",
            ),
            "content_indexing_failed": (
                self._entry(
                    AuditAction.UPDATE,
                    "document",
                    self.document.pk,
                    {
                        "event": "CONTENT_INDEXED",
                        "status": "FAILURE",
                        "detail": "Content indexing failed: RuntimeError.",
                        "document_code": self.document.code,
                    },
                ),
                INGESTION_FAILURE,
                FAILURE,
                "CONTENT_INDEXING_FAILED",
            ),
            "registered": (
                self._entry(
                    AuditAction.DOC_SUBMIT_SUCCESS,
                    "document",
                    self.document.pk,
                    {"document_code": self.document.code, "version": 1},
                ),
                UPLOAD,
                SUCCESS,
                "DOCUMENT_REGISTERED",
            ),
            "seed_created": (
                self._entry(
                    AuditAction.CREATE, "document", self.document.pk, {"code": self.document.code}
                ),
                UPLOAD,
                SUCCESS,
                "DOCUMENT_REGISTERED",
            ),
            "revision": (
                self._entry(
                    AuditAction.DOC_REVISION_CREATED,
                    "document",
                    self.document.pk,
                    {"document_code": self.document.code, "version": 2},
                ),
                REVISION,
                SUCCESS,
                "REVISION_SUBMITTED",
            ),
            "seed_revision": (
                self._entry(
                    AuditAction.CREATE,
                    "revision",
                    self.revision.pk,
                    {"document_id": self.document.pk, "version": 1},
                ),
                REVISION,
                SUCCESS,
                "REVISION_SUBMITTED",
            ),
            "revision_rejected": (
                self._entry(
                    AuditAction.UPDATE,
                    "revision",
                    self.revision.pk,
                    {"event": "REVISION_REJECTED", "version": 1, "justification": "Fora da norma"},
                    user=self.manager,
                ),
                MODERATION,
                SUCCESS,
                "REVISION_REJECTED",
            ),
            "seed_revision_decided": (
                self._entry(
                    AuditAction.UPDATE,
                    "revision",
                    self.revision.pk,
                    {"document_id": self.document.pk, "version": 1, "status": "APPROVED"},
                    user=self.manager,
                ),
                MODERATION,
                SUCCESS,
                "REVISION_APPROVED",
            ),
            "access_approved": (
                self._entry(
                    AuditAction.UPDATE,
                    "document_access",
                    self.access.pk,
                    {"event": "ACCESS_APPROVED", "document_id": self.document.pk},
                    user=self.manager,
                ),
                MODERATION,
                SUCCESS,
                "ACCESS_APPROVED",
            ),
            "archived": (
                self._entry(
                    AuditAction.DELETE,
                    "document",
                    self.document.pk,
                    {"event": "DOCUMENT_ARCHIVED", "document_code": self.document.code},
                    user=self.manager,
                ),
                MODERATION,
                SUCCESS,
                "DOCUMENT_ARCHIVED",
            ),
            "restored": (
                self._entry(
                    AuditAction.UPDATE,
                    "document",
                    self.document.pk,
                    {"event": "DOCUMENT_RESTORED", "document_code": self.document.code},
                    user=self.manager,
                ),
                MODERATION,
                SUCCESS,
                "DOCUMENT_RESTORED",
            ),
            "access_requested": (
                self._entry(
                    AuditAction.DOC_ACCESS_REQUESTED,
                    "document",
                    self.document.pk,
                    {"document_code": self.document.code, "justification": "Preciso"},
                    user=self.outsider,
                ),
                ACCESS,
                SUCCESS,
                "ACCESS_REQUESTED",
            ),
            "seed_access_requested": (
                self._entry(
                    AuditAction.CREATE,
                    "document_access",
                    self.access.pk,
                    {"document_id": self.document.pk},
                    user=self.outsider,
                ),
                ACCESS,
                SUCCESS,
                "ACCESS_REQUESTED",
            ),
            "access_denied": (
                self._entry(
                    AuditAction.READ,
                    "document",
                    self.document.pk,
                    {"event": "DOCUMENT_ACCESS_DENIED", "document_code": self.document.code},
                    user=self.outsider,
                ),
                ACCESS,
                FAILURE,
                "DOCUMENT_ACCESS_DENIED",
            ),
            "seed_viewed": (
                self._entry(AuditAction.READ, "document", self.document.pk, None),
                ACCESS,
                SUCCESS,
                "DOCUMENT_VIEWED",
            ),
        }

        by_id = {item["id"]: item for item in self._results({"page_size": "100"})}

        self.assertEqual(len(by_id), len(cases))
        for name, (entry, event_type, status, event) in cases.items():
            with self.subTest(case=name):
                item = by_id[entry.pk]
                self.assertEqual(
                    (item["event_type"], item["status"], item["event"]), (event_type, status, event)
                )

    def test_should_describe_the_events_for_people(self):
        failure = self._upload_entry("FAILURE", "Text extraction failed: PdfReadError.")
        rejected = self._entry(
            AuditAction.UPDATE,
            "revision",
            self.revision.pk,
            {"event": "REVISION_REJECTED", "version": 1, "justification": "Fora da norma"},
            user=self.manager,
        )
        duplicate = self._entry(
            AuditAction.DOC_UPLOAD_DUPLICATE,
            "document",
            self.document.pk,
            {"stage": "upload", "document_code": self.document.code, "original_name": "x.pdf"},
        )

        by_id = {item["id"]: item for item in self._results()}

        self.assertEqual(by_id[failure.pk]["detail"], "Text extraction failed: PdfReadError.")
        self.assertEqual(by_id[failure.pk]["file"], "caverna-14.pdf")
        self.assertIsNone(by_id[failure.pk]["document"])
        self.assertEqual(
            by_id[rejected.pk]["detail"],
            f"Revision REV01 of document {self.document.code} rejected. "
            "Justification: Fora da norma",
        )
        self.assertEqual(by_id[rejected.pk]["revision"], "REV01")
        self.assertEqual(by_id[rejected.pk]["document"]["title"], self.document.title)
        self.assertEqual(by_id[duplicate.pk]["file"], "x.pdf")
        self.assertIn(self.document.code, by_id[duplicate.pk]["detail"])

    def test_should_keep_the_document_code_when_the_document_no_longer_exists(self):
        entry = self._entry(
            AuditAction.DOC_SUBMIT_SUCCESS,
            "document",
            self.document.pk,
            {"document_code": self.document.code},
        )
        self.access.delete()
        self.revision.delete()
        self.document.delete()

        results = self._results()

        self.assertEqual(results, [])
        self.assertIsNotNone(entry.pk)


class ActivityQueryTests(ManagerActivityFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        for minute in range(3):
            self._upload_entry(minutes_ago=minute)
        self._entry(
            AuditAction.DOC_REVISION_CREATED,
            "document",
            self.document.pk,
            {"document_code": self.document.code, "version": 2},
            minutes_ago=10,
        )
        self._upload_entry("FAILURE", "Text extraction failed: PdfReadError.", minutes_ago=20)

    def test_should_filter_by_one_or_more_event_types(self):
        single = list_activities(self.manager, {"type": "revision"})
        several = list_activities(self.manager, {"type": "REVISION,INGESTION_FAILURE"})
        everything = list_activities(self.manager, {})

        self.assertEqual([item["event_type"] for item in single["results"]], [REVISION])
        self.assertEqual(
            [item["event_type"] for item in several["results"]], [REVISION, INGESTION_FAILURE]
        )
        self.assertEqual(everything["count"], 5)

    def test_should_paginate_with_page_size_or_the_limit_alias(self):
        first = list_activities(self.manager, {"page_size": "2"})
        last = list_activities(self.manager, {"limit": "2", "page": "3"})
        beyond = list_activities(self.manager, {"limit": "2", "page": "9"})

        self.assertEqual((first["count"], first["total_pages"], first["page_size"]), (5, 3, 2))
        self.assertEqual(len(first["results"]), 2)
        self.assertEqual([item["event_type"] for item in last["results"]], [INGESTION_FAILURE])
        self.assertEqual(beyond["results"], [])
        self.assertEqual(beyond["current_page"], 9)

    def test_should_reject_invalid_parameters(self):
        with self.assertRaises(ActivityQueryError) as context:
            parse_activity_query({"type": "UPLOAD,SOMETHING", "page": "0", "limit": "500"})

        self.assertEqual(context.exception.errors["type"]["code"], "invalid_choice")
        self.assertEqual(context.exception.errors["page"]["code"], "invalid")
        self.assertEqual(context.exception.errors["limit"]["code"], "too_large")


class ManagerActivitiesViewTests(ManagerActivityFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("manager-activities")
        self._upload_entry()

    def test_should_return_the_activity_feed_to_a_manager(self):
        self.client.force_login(self.manager)

        response = self.client.get(self.url, {"type": "UPLOAD"})

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(
            set(body["results"][0]),
            {
                "id",
                "timestamp",
                "user",
                "document",
                "file",
                "revision",
                "event_type",
                "event",
                "status",
                "detail",
            },
        )
        self.assertEqual(body["results"][0]["user"], {"id": self.author.pk, "name": "Author"})

    def test_should_require_authentication_and_the_manager_role(self):
        anonymous = self.client.get(self.url)
        self.client.force_login(self.author)
        forbidden = self.client.get(self.url)

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.json(), {"error": "AuthenticationRequired"})
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json(), {"error": "PermissionDenied"})

    def test_should_answer_400_for_invalid_parameters(self):
        self.client.force_login(self.manager)

        response = self.client.get(self.url, {"type": "OTHER", "page": "x"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"type", "page"})

    def test_should_reject_other_methods_and_hide_internal_errors(self):
        self.client.force_login(self.manager)

        rejected = self.client.post(self.url)
        with mock.patch(
            "core.views.manager_activity_view.list_activities",
            side_effect=RuntimeError("db at 10.0.0.1"),
        ):
            failed = self.client.get(self.url)

        self.assertEqual(rejected.status_code, 405)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(failed.json(), {"error": "RuntimeError"})


@mock.patch("core.services.temp_upload_service.get_mongo_db")
class IngestionOutcomeOnUploadTests(ManagerActivityFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.client.force_login(self.author)

    def _upload(self, name, content):
        with override_settings(TEMP_UPLOAD_DIR=self.temp_dir, MAX_UPLOAD_SIZE_BYTES=1024 * 1024):
            return self.client.post(
                reverse("document-upload"), {"file": SimpleUploadedFile(name, content)}
            )

    def test_should_record_the_extraction_failure_and_show_it_to_the_manager(self, mongo):
        response = self._upload("relatorio.pdf", PDF_HEADER)

        entry = AuditLog.objects.get(action=AuditAction.DOC_UPLOAD_SUCCESS)
        self.client.force_login(self.manager)
        feed = self.client.get(reverse("manager-activities"), {"type": "INGESTION_FAILURE"}).json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.record["ingestion"]["extraction"], "FAILURE")
        self.assertTrue(entry.record["ingestion"]["detail"].startswith("Text extraction failed:"))
        self.assertEqual(feed["count"], 1)
        self.assertEqual(feed["results"][0]["file"], "relatorio.pdf")
        self.assertEqual(feed["results"][0]["status"], FAILURE)

    def test_should_record_a_skipped_extraction_for_images(self, mongo):
        response = self._upload("foto.png", b"\x89PNG\r\n\x1a\n fake png body")

        entry = AuditLog.objects.get(action=AuditAction.DOC_UPLOAD_SUCCESS)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.record["ingestion"]["extraction"], "SKIPPED")

    @mock.patch(
        "core.services.temp_upload_service.ingest_text",
        return_value={"text": "texto", "extraction": "SUCCESS", "detail": None},
    )
    def test_should_record_a_successful_extraction(self, ingest, mongo):
        response = self._upload("relatorio.pdf", PDF_HEADER)

        entry = AuditLog.objects.get(action=AuditAction.DOC_UPLOAD_SUCCESS)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(entry.record["ingestion"], {"extraction": "SUCCESS", "detail": None})


@mock.patch("core.services.document_ai_service.get_mongo_db")
@mock.patch("core.services.document_ai_service.get_classifier")
class ClassificationOutcomeTests(ManagerActivityFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.settings_override = override_settings(TEMP_UPLOAD_DIR=self.temp_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        Path(self.temp_dir, f"{TEMP_FILE_ID}.pdf").write_bytes(b"conteudo")
        self.client.force_login(self.author)

    def _suggest(self):
        return self.client.post(reverse("document-ai-suggestions", args=[TEMP_FILE_ID]))

    def _classification_entry(self):
        return AuditLog.objects.get(record__event="AI_CLASSIFICATION")

    @mock.patch(
        "core.services.document_ai_service.get_temp_upload_record",
        return_value={"extracted_text": "texto processado"},
    )
    def test_should_record_a_failed_classification(self, record, classifier, mongo):
        classifier.return_value.predict.side_effect = RuntimeError("boom")

        response = self._suggest()

        entry = self._classification_entry()
        self.client.force_login(self.manager)
        feed = self.client.get(reverse("manager-activities"), {"type": "INGESTION_FAILURE"}).json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(entry.record["status"], "FAILURE")
        self.assertEqual(entry.record["temp_file_id"], TEMP_FILE_ID)
        self.assertEqual(feed["results"][0]["event"], "AI_CLASSIFICATION_FAILED")
        self.assertEqual(feed["results"][0]["user"]["id"], self.author.pk)

    @mock.patch(
        "core.services.document_ai_service.get_temp_upload_record",
        return_value={"extracted_text": "texto processado"},
    )
    def test_should_record_a_successful_classification(self, record, classifier, mongo):
        classifier.return_value.predict.return_value = {
            "discipline": Prediction("MECHANICAL", 0.9),
            "document_type": Prediction("SPECIFICATION", 0.8),
            "area": Prediction("DESIGN", 0.7),
        }

        response = self._suggest()

        entry = self._classification_entry()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["discipline"]["name"], "Estruturas")
        self.assertNotIn("classification", response.json())
        self.assertEqual(entry.record["status"], "SUCCESS")

    @mock.patch(
        "core.services.document_ai_service.get_temp_upload_record",
        return_value={"extracted_text": ""},
    )
    def test_should_record_a_skipped_classification_without_text(self, record, classifier, mongo):
        response = self._suggest()

        entry = self._classification_entry()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(entry.record["status"], "SKIPPED")
        classifier.return_value.predict.assert_not_called()


@mock.patch("core.services.document_creation_service.get_mongo_db")
class ContentIndexingOutcomeTests(ManagerActivityFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.project.disciplines.add(self.discipline)
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        self.settings_override = override_settings(
            TEMP_UPLOAD_DIR=self.temp_dir, DOCUMENT_STORAGE_DIR=self.storage_dir
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        docx = DocxDocument()
        docx.add_paragraph("A fundação da ponte usa estacas. A ponte e a fundação foram revisadas.")
        docx.save(Path(self.temp_dir) / f"{TEMP_FILE_ID}.docx")
        self.payload = {
            "temp_file_id": TEMP_FILE_ID,
            "title": "Memorial da ponte",
            "project_id": self.project.id,
            "discipline_id": self.discipline.id,
            "document_type": self.document_type.id,
            "confidentiality": "CONFIDENTIAL",
            "responsible_id": self.author.id,
            "user_id": self.author.id,
            "areas": ["EST"],
        }

    def _indexing_entry(self):
        return AuditLog.objects.get(record__event="CONTENT_INDEXED")

    def test_should_record_the_indexing_of_a_created_document_for_its_area(self, mongo):
        document = document_creation_service.create_document(self.payload)

        entry = self._indexing_entry()
        self.client.force_login(self.manager)
        feed = self.client.get(reverse("manager-activities"), {"type": "UPLOAD"}).json()
        item = next(item for item in feed["results"] if item["event"] == "CONTENT_INDEXED")
        self.assertEqual(entry.entity_id, document.pk)
        self.assertEqual(entry.user, self.author)
        self.assertEqual(entry.record["status"], "SUCCESS")
        self.assertEqual(entry.record["thematic_tag_count"], 2)
        self.assertGreater(entry.record["content_chars"], 0)
        self.assertEqual(item["document"]["code"], document.code)
        self.assertEqual(item["revision"], "REV01")
        self.assertEqual(item["status"], SUCCESS)

    def test_should_record_a_failed_indexing_without_blocking_the_registration(self, mongo):
        with mock.patch(
            "core.services.document_index_service.index_document",
            side_effect=RuntimeError("boom"),
        ):
            document = document_creation_service.create_document(self.payload)

        entry = self._indexing_entry()
        self.client.force_login(self.manager)
        feed = self.client.get(reverse("manager-activities"), {"type": "INGESTION_FAILURE"}).json()
        self.assertEqual(Document.objects.filter(pk=document.pk).count(), 1)
        self.assertEqual(entry.record["status"], "FAILURE")
        self.assertEqual(entry.record["detail"], "Content indexing failed: RuntimeError.")
        self.assertEqual(feed["count"], 1)
        self.assertEqual(feed["results"][0]["event"], "CONTENT_INDEXING_FAILED")
        self.assertEqual(feed["results"][0]["document"]["id"], document.pk)
