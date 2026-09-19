from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentType,
    Project,
    Revision,
    RevisionStatus,
    User,
)
from core.services.documents_service import build_simple_filters


class DocumentsViewTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.project.disciplines.add(self.discipline)
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.user = User.objects.create_user(
            email="user@example.com",
            password="test-password",
            name="User",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-001",
            title="Relatório de engenharia",
            description="Memorial descritivo",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.user,
            created_at=timezone.now() - timedelta(days=2),
            updated_at=timezone.now() - timedelta(days=1),
        )
        self.document.areas.add(self.area)
        self.client = Client()

    def test_returns_all_active_documents_without_filters(self):
        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["code"], "DOC-001")

    def test_filters_documents_by_query_and_area(self):
        response = self.client.get("/documents", {"q": "memorial", "area": "ENG"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["code"] for item in response.json()["results"]], ["DOC-001"])

    def test_returns_empty_list_when_filter_does_not_match(self):
        response = self.client.get("/documents", {"tipo": "DWG"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"count": 0, "total_pages": 1, "current_page": 1, "page_size": 20, "results": []},
        )

    def _other_document(self, code):
        document = Document.objects.create(
            code=code,
            title=code,
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.user,
        )
        document.areas.add(self.area)
        return document

    def test_should_return_null_status_for_a_document_without_revisions(self):
        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["results"][0]["status"])

    def test_should_return_the_status_of_the_only_revision(self):
        Revision.objects.create(document=self.document, version=1, author=self.user)

        response = self.client.get("/documents")

        self.assertEqual(response.json()["results"][0]["status"], "PENDING")

    def test_should_return_the_status_of_the_most_recent_revision(self):
        auditor = User.objects.create_user(
            email="auditor@example.com", password="test-password", name="Auditor", area=self.area
        )
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.user,
            auditor=auditor,
            audited_at=timezone.now(),
        )
        Revision.objects.create(
            document=self.document, version=2, status=RevisionStatus.PENDING, author=self.user
        )

        response = self.client.get("/documents")

        self.assertEqual(response.json()["results"][0]["status"], "PENDING")

    def test_should_keep_the_status_when_filters_are_applied(self):
        Revision.objects.create(document=self.document, version=1, author=self.user)

        response = self.client.get("/documents", {"q": "memorial", "area": "ENG"})

        self.assertEqual(
            [(item["code"], item["status"]) for item in response.json()["results"]],
            [("DOC-001", "PENDING")],
        )

    def test_should_not_run_one_status_query_per_document(self):
        for index in range(4):
            document = self._other_document(f"DOC-10{index}")
            Revision.objects.create(document=document, version=1, author=self.user)

        with self.assertNumQueries(4):
            response = self.client.get("/documents")

        self.assertEqual(len(response.json()["results"]), 5)


class SimpleFiltersViewTests(TestCase):
    def setUp(self):
        cache.clear()
        Area.objects.create(acronym="ENG", name="Engenharia", active=True)
        Area.objects.create(acronym="OLD", name="Desativada", active=False)
        DocumentType.objects.create(code="PDF", name="Relatório", active=True)
        DocumentType.objects.create(code="OLD", name="Desativado", active=False)
        self.client = Client()

    def test_returns_active_filter_groups(self):
        response = self.client.get("/documents/simple-filters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"areas", "types", "dates"})
        self.assertEqual(response.json()["areas"], [{"acronym": "ENG", "name": "Engenharia"}])
        self.assertEqual(response.json()["types"], [{"code": "PDF", "name": "Relatório"}])
        self.assertTrue(response.json()["dates"])

    @mock.patch("core.services.documents_service.cache")
    def test_uses_cached_filter_groups(self, mocked_cache):
        mocked_cache.get.return_value = {"areas": [], "types": [], "dates": []}

        response = self.client.get("/documents/simple-filters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"areas": [], "types": [], "dates": []})
        mocked_cache.set.assert_not_called()

    def test_builds_filter_groups_with_expected_shape(self):
        self.assertEqual(set(build_simple_filters()), {"areas", "types", "dates"})
