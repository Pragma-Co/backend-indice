import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from docx import Document as DocxDocument

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentAccess,
    DocumentContent,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    Tag,
    User,
)
from core.models.choices import AccessStatus
from core.services import document_creation_service
from core.services.document_index_service import (
    generate_thematic_tags,
    index_document,
    index_document_safely,
    save_document_content,
)

BRIDGE_TEXT = (
    "O memorial de cálculo da ponte descreve a fundação, as vigas e a armadura da ponte. "
    "A fundação da ponte usa estacas de concreto armado."
)


class DocumentSearchTestCase(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.project.disciplines.add(self.discipline)
        self.document_type = DocumentType.objects.create(code="MEM", name="Memorial")
        self.owner = User.objects.create_user(
            email="owner@example.com", password="secret", name="Owner", area=self.area
        )
        self.reader = User.objects.create_user(
            email="reader@example.com", password="secret", name="Reader", area=self.area
        )
        self.client = Client()

    def _document(self, code, title, description="", content=None):
        document = Document.objects.create(
            code=code,
            title=title,
            description=description,
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.owner,
            created_by=self.owner,
            updated_by=self.owner,
        )
        document.areas.add(self.area)
        revision = Revision.objects.create(
            document=document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.owner,
            auditor=self.owner,
            audited_at=timezone.now(),
        )
        if content is not None:
            save_document_content(document, revision, content)
        return document

    def _search(self, **params):
        return self.client.get(reverse("document-search"), params)

    def _codes(self, response):
        return [item["code"] for item in response.json()["results"]]


class ThematicTagGenerationTests(DocumentSearchTestCase):
    def test_should_generate_thematic_tags_ordered_by_frequency_without_stopwords(self):
        content = BRIDGE_TEXT

        tags = generate_thematic_tags(content)

        self.assertEqual(tags, ["ponte", "fundação"])

    def test_should_ignore_words_that_appear_only_once(self):
        content = "Relatório único sobre hidráulica"

        tags = generate_thematic_tags(content)

        self.assertEqual(tags, [])


class DocumentIndexServiceTests(DocumentSearchTestCase):
    def setUp(self):
        super().setUp()
        self.storage_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.storage_dir, ignore_errors=True)
        self.settings_override = override_settings(DOCUMENT_STORAGE_DIR=self.storage_dir)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def _write_docx(self, path, paragraphs):
        path.parent.mkdir(parents=True, exist_ok=True)
        docx = DocxDocument()
        for paragraph in paragraphs:
            docx.add_paragraph(paragraph)
        docx.save(path)

    def _attach_docx(self, revision, storage_path, paragraphs):
        self._write_docx(Path(self.storage_dir) / storage_path, paragraphs)
        return File.objects.create(
            revision=revision,
            original_name="memorial.docx",
            extension="docx",
            mime_type="application/octet-stream",
            size_bytes=1,
            sha256=f"{revision.version:064x}",
            storage_path=storage_path,
        )

    def test_should_index_normalized_text_of_the_latest_revision(self):
        document = self._document("MEM-001", "Memorial")
        first_revision = document.revisions.get()
        self._attach_docx(first_revision, "v1/memorial.docx", ["Texto antigo"])
        latest_revision = Revision.objects.create(document=document, version=2, author=self.owner)
        self._attach_docx(latest_revision, "v2/memorial.docx", [BRIDGE_TEXT, "  Anexo\tfinal  "])

        indexed = index_document(document)

        self.assertEqual(indexed.revision, latest_revision)
        self.assertEqual(indexed.content, f"{BRIDGE_TEXT} Anexo final")
        self.assertEqual(indexed.thematic_tags, ["ponte", "fundação"])
        self.assertIsNotNone(DocumentContent.objects.get(pk=document.pk).search_vector)

    def test_should_index_empty_content_when_the_file_cannot_be_read(self):
        document = self._document("MEM-001", "Memorial")
        File.objects.create(
            revision=document.revisions.get(),
            original_name="missing.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=1,
            sha256="a" * 64,
            storage_path="missing.pdf",
        )

        indexed = index_document(document)

        self.assertEqual(indexed.content, "")
        self.assertEqual(indexed.thematic_tags, [])

    def test_should_not_raise_when_indexing_fails(self):
        document = self._document("MEM-001", "Memorial")

        with mock.patch(
            "core.services.document_index_service.index_document",
            side_effect=RuntimeError("boom"),
        ):
            index_document_safely(document)

        self.assertFalse(DocumentContent.objects.filter(pk=document.pk).exists())

    @mock.patch("core.services.document_creation_service.get_mongo_db")
    def test_should_index_the_document_content_when_the_document_is_created(self, mongo):
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        temp_file_id = "11111111-2222-4333-8444-555555555555"
        self._write_docx(Path(temp_dir) / f"{temp_file_id}.docx", [BRIDGE_TEXT])
        payload = {
            "temp_file_id": temp_file_id,
            "title": "Memorial da ponte",
            "project_id": self.project.id,
            "discipline_id": self.discipline.id,
            "document_type": self.document_type.id,
            "confidentiality": "CONFIDENTIAL",
            "responsible_id": self.owner.id,
            "areas": ["EST"],
        }

        with override_settings(TEMP_UPLOAD_DIR=temp_dir):
            document = document_creation_service.create_document(payload)

        indexed = DocumentContent.objects.get(pk=document.pk)
        self.assertEqual(indexed.content, BRIDGE_TEXT)
        self.assertEqual(indexed.thematic_tags, ["ponte", "fundação"])

    @mock.patch("core.services.document_creation_service.get_mongo_db")
    def test_should_reindex_the_document_content_when_a_revision_is_created(self, mongo):
        document = self._document("MEM-001", "Memorial", content="Texto antigo")
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        temp_file_id = "11111111-2222-4333-8444-666666666666"
        self._write_docx(Path(temp_dir) / f"{temp_file_id}.docx", [BRIDGE_TEXT])

        with override_settings(TEMP_UPLOAD_DIR=temp_dir):
            revision = document_creation_service.create_document_revision(
                document.id, [temp_file_id], "Atualiza o memorial da ponte"
            )

        indexed = DocumentContent.objects.get(pk=document.pk)
        self.assertEqual(indexed.revision, revision)
        self.assertEqual(indexed.content, BRIDGE_TEXT)
        self.assertEqual(indexed.thematic_tags, ["ponte", "fundação"])


class DocumentSearchViewTests(DocumentSearchTestCase):
    def test_should_return_content_matches_with_highlighted_snippets_to_the_owner(self):
        self._document("MEM-001", "Memorial descritivo", content=BRIDGE_TEXT)
        self.client.force_login(self.owner)

        response = self._search(q="estacas")

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["code"], "MEM-001")
        self.assertTrue(result["content_match"])
        self.assertEqual(len(result["highlights"]["content"]), 1)
        self.assertIn("<mark>estacas</mark>", result["highlights"]["content"][0])

    def test_should_hide_content_only_matches_from_users_without_access(self):
        self._document("MEM-001", "Memorial descritivo", content=BRIDGE_TEXT)
        self.client.force_login(self.reader)

        response = self._search(q="estacas")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_should_hide_content_only_matches_from_anonymous_users(self):
        self._document("MEM-001", "Memorial descritivo", content=BRIDGE_TEXT)

        response = self._search(q="estacas")

        self.assertEqual(response.json()["count"], 0)

    def test_should_return_content_matches_to_users_with_approved_access(self):
        document = self._document("MEM-001", "Memorial descritivo", content=BRIDGE_TEXT)
        DocumentAccess.objects.create(
            document=document,
            user=self.reader,
            status=AccessStatus.APPROVED,
            approver=self.owner,
            decided_at=timezone.now(),
        )
        self.client.force_login(self.reader)

        response = self._search(q="estacas")

        self.assertEqual(self._codes(response), ["MEM-001"])

    def test_should_not_send_content_snippets_when_only_metadata_matches(self):
        self._document("MEM-001", "Memorial da ponte", content=BRIDGE_TEXT)
        self.client.force_login(self.reader)

        response = self._search(q="ponte")

        result = response.json()["results"][0]
        self.assertFalse(result["content_match"])
        self.assertEqual(result["highlights"]["content"], [])
        self.assertEqual(result["highlights"]["title"], "Memorial da <mark>ponte</mark>")

    def test_should_find_documents_by_generated_thematic_tags(self):
        self._document("MEM-001", "Memorial descritivo", content=BRIDGE_TEXT)
        self.client.force_login(self.owner)

        response = self._search(q="fundação")

        result = response.json()["results"][0]
        self.assertEqual(result["code"], "MEM-001")
        self.assertEqual(result["thematic_tags"], ["ponte", "fundação"])
        self.assertEqual(result["matched_tags"], ["fundação"])

    def test_should_not_match_thematic_tags_for_users_without_access(self):
        self._document("MEM-001", "Memorial descritivo", content=BRIDGE_TEXT)
        self.client.force_login(self.reader)

        response = self._search(q="fundação")

        self.assertEqual(response.json()["count"], 0)

    def test_should_not_match_thematic_tags_for_anonymous_users(self):
        self._document("MEM-001", "Memorial descritivo", content=BRIDGE_TEXT)

        response = self._search(q="fundação")

        self.assertEqual(response.json()["count"], 0)

    def test_should_not_expose_thematic_tags_to_users_without_access(self):
        self._document("MEM-001", "Memorial da ponte", content=BRIDGE_TEXT)
        self.client.force_login(self.reader)

        response = self._search(q="ponte")

        result = response.json()["results"][0]
        self.assertEqual(result["thematic_tags"], [])
        self.assertEqual(result["matched_tags"], [])

    def test_should_find_documents_by_manual_tags(self):
        document = self._document("MEM-001", "Memorial descritivo")
        document.tags.add(Tag.objects.create(name="Hidráulica"))

        response = self._search(q="hidraulica")

        result = response.json()["results"][0]
        self.assertEqual(result["tags"], ["Hidráulica"])
        self.assertEqual(result["matched_tags"], ["Hidráulica"])

    def test_should_ignore_accents_and_word_inflection(self):
        self._document("MEM-001", "Memorial de Cálculo das Vigas")

        response = self._search(q="calculo viga")

        result = response.json()["results"][0]
        self.assertEqual(
            result["highlights"]["title"],
            "Memorial de <mark>Cálculo</mark> das <mark>Vigas</mark>",
        )

    def test_should_rank_metadata_matches_above_content_only_matches(self):
        self._document("MEM-001", "Relatório geral", content=BRIDGE_TEXT)
        self._document("MEM-002", "Memorial das estacas")
        self.client.force_login(self.owner)

        response = self._search(q="estacas")

        self.assertEqual(self._codes(response), ["MEM-002", "MEM-001"])
        scores = [item["score"] for item in response.json()["results"]]
        self.assertGreater(scores[0], scores[1])

    def test_should_rank_documents_matching_more_terms_first(self):
        self._document("MEM-001", "Memorial da ponte")
        self._document("MEM-002", "Memorial da ponte e da fundação")

        response = self._search(q="ponte fundação")

        self.assertEqual(self._codes(response), ["MEM-002", "MEM-001"])

    def test_should_escape_html_from_the_document_content(self):
        content = "Vigas <script>alert(1)</script> 5 < 10 & ponte"
        self._document("MEM-001", "Memorial", content=content)
        self.client.force_login(self.owner)

        response = self._search(q="ponte")

        snippet = response.json()["results"][0]["highlights"]["content"][0]
        self.assertNotIn("<script>", snippet)
        self.assertIn("5 &lt; 10 &amp; <mark>ponte</mark>", snippet)

    def test_should_not_return_archived_documents(self):
        document = self._document("MEM-001", "Memorial da ponte")
        Document.objects.filter(pk=document.pk).update(
            archived_at=timezone.now(), archived_by=self.owner
        )

        response = self._search(q="ponte")

        self.assertEqual(response.json()["count"], 0)

    def test_should_combine_the_search_with_listing_filters(self):
        self._document("MEM-001", "Memorial da ponte")
        other_type = DocumentType.objects.create(code="DWG", name="Desenho")
        other = self._document("DWG-001", "Desenho da ponte")
        Document.objects.filter(pk=other.pk).update(document_type=other_type)

        response = self._search(q="ponte", tipo="DWG")

        self.assertEqual(self._codes(response), ["DWG-001"])

    def test_should_paginate_results(self):
        for number in range(3):
            self._document(f"MEM-00{number}", f"Memorial da ponte {number}")

        response = self._search(q="ponte", page_size=2, page=2)

        body = response.json()
        self.assertEqual((body["count"], body["total_pages"], body["current_page"]), (3, 2, 2))
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(body["query"], "ponte")

    def test_should_reject_a_missing_query(self):
        response = self._search()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["q"]["code"], "required")

    def test_should_reject_a_query_without_words(self):
        response = self._search(q="?!")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["q"]["code"], "invalid")

    def test_should_reject_a_query_that_is_too_long(self):
        response = self._search(q="a" * 201)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["q"]["code"], "too_long")

    def test_should_report_query_and_pagination_errors_together(self):
        response = self._search(page="0")

        self.assertEqual(set(response.json()["errors"]), {"q", "page"})

    def test_should_reject_methods_other_than_get(self):
        response = self.client.post(reverse("document-search"), {"q": "ponte"})

        self.assertEqual(response.status_code, 405)

    def test_should_hide_internal_errors(self):
        with mock.patch(
            "core.views.documents_view.search_documents",
            side_effect=RuntimeError("db at 10.0.0.1"),
        ):
            response = self._search(q="ponte")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})


class IndexDocumentsCommandTests(DocumentSearchTestCase):
    def test_should_index_every_document(self):
        self._document("MEM-001", "Memorial")
        self._document("MEM-002", "Desenho")
        stdout = StringIO()

        call_command("index_documents", stdout=stdout)

        self.assertEqual(DocumentContent.objects.count(), 2)
        self.assertIn("Indexed 2 documents, 0 failed.", stdout.getvalue())

    def test_should_only_index_documents_never_indexed_when_asked(self):
        self._document("MEM-001", "Memorial", content=BRIDGE_TEXT)
        self._document("MEM-002", "Desenho")
        stdout = StringIO()

        call_command("index_documents", "--missing-only", stdout=stdout)

        self.assertEqual(DocumentContent.objects.get(document__code="MEM-001").content, BRIDGE_TEXT)
        self.assertIn("Indexed 1 documents, 0 failed.", stdout.getvalue())
