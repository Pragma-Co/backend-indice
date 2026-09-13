from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from core.models import Area, Discipline, Document, DocumentType, Project, User
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
        self.assertEqual(response.json()["documents"][0]["code"], "DOC-001")

    def test_filters_documents_by_query_and_area(self):
        response = self.client.get("/documents", {"q": "memorial", "area": "ENG"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["code"] for item in response.json()["documents"]], ["DOC-001"])

    def test_returns_empty_list_when_filter_does_not_match(self):
        response = self.client.get("/documents", {"tipo": "DWG"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"documents": []})


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
        self.assertEqual(set(response.json()), {"areas", "tipos", "datas"})
        self.assertEqual(response.json()["areas"], [{"acronym": "ENG", "name": "Engenharia"}])
        self.assertEqual(response.json()["tipos"], [{"code": "PDF", "name": "Relatório"}])
        self.assertTrue(response.json()["datas"])

    @mock.patch("core.services.documents_service.cache")
    def test_uses_cached_filter_groups(self, mocked_cache):
        mocked_cache.get.return_value = {"areas": [], "tipos": [], "datas": []}

        response = self.client.get("/documents/simple-filters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"areas": [], "tipos": [], "datas": []})
        mocked_cache.set.assert_not_called()

    def test_builds_filter_groups_with_expected_shape(self):
        self.assertEqual(set(build_simple_filters()), {"areas", "tipos", "datas"})
