from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    Project,
    Revision,
    User,
)
from core.models.choices import AccessStatus, RevisionStatus
from core.services.documents_exceptions import (
    DocumentNotFoundError,
    MissingUserError,
    UserNotFoundError,
)
from core.services.documents_service import (
    build_simple_filters,
    get_document_detail,
    request_document_access,
)


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


class DocumentDetailServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="test-password",
            name="Other",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-100",
            title="Relatório de engenharia",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )
        self.document.areas.add(self.area)
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.responsible,
            auditor=self.responsible,
            audited_at=timezone.now(),
        )

    def test_should_return_document_not_found_for_missing_id(self):
        with self.assertRaises(DocumentNotFoundError):
            get_document_detail(999999)

    def test_should_return_document_not_found_when_type_is_inactive(self):
        self.document_type.active = False
        self.document_type.save()

        with self.assertRaises(DocumentNotFoundError):
            get_document_detail(self.document.id)

    def test_should_return_pending_access_when_no_user_is_given(self):
        detail = get_document_detail(self.document.id)

        self.assertEqual(detail["access_status"], "PENDING")

    def test_should_return_approved_access_for_the_document_responsible(self):
        detail = get_document_detail(self.document.id, user_id=self.responsible.id)

        self.assertEqual(detail["access_status"], "APPROVED")

    def test_should_return_approved_access_when_user_has_a_grant(self):
        DocumentAccess.objects.create(
            document=self.document,
            user=self.other_user,
            status=AccessStatus.APPROVED,
            approver=self.responsible,
            decided_at=timezone.now(),
        )

        detail = get_document_detail(self.document.id, user_id=self.other_user.id)

        self.assertEqual(detail["access_status"], "APPROVED")

    def test_should_return_pending_access_for_a_user_without_grant(self):
        detail = get_document_detail(self.document.id, user_id=self.other_user.id)

        self.assertEqual(detail["access_status"], "PENDING")

    def test_should_return_in_review_access_when_current_revision_is_pending(self):

        self.document.revisions.all().delete()
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.PENDING,
            author=self.responsible,
        )

        detail = get_document_detail(self.document.id, user_id=self.other_user.id)

        self.assertEqual(detail["access_status"], "IN_REVIEW")

    def test_should_include_consolidated_metadata_in_the_response(self):
        detail = get_document_detail(self.document.id, user_id=self.responsible.id)

        self.assertEqual(detail["code"], "DOC-100")
        self.assertEqual(detail["project"]["code"], "PRJ")
        self.assertEqual(detail["discipline"]["code"], "CIV")
        self.assertEqual(detail["type"]["code"], "PDF")
        self.assertEqual(detail["responsible"]["email"], "responsible@example.com")
        self.assertEqual(detail["revision"]["version"], 1)
        self.assertEqual(detail["revision"]["status"], "APPROVED")
        self.assertEqual([a["acronym"] for a in detail["areas"]], ["ENG"])


class DocumentAccessRequestServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible2@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.requester = User.objects.create_user(
            email="requester@example.com",
            password="test-password",
            name="Requester",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-200",
            title="Documento restrito",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )

    def test_should_raise_document_not_found_for_missing_document(self):
        with self.assertRaises(DocumentNotFoundError):
            request_document_access(999999, self.requester.id)

    def test_should_raise_missing_user_when_no_user_id_is_given(self):
        with self.assertRaises(MissingUserError):
            request_document_access(self.document.id, None)

    def test_should_raise_user_not_found_for_unknown_user_id(self):
        with self.assertRaises(UserNotFoundError):
            request_document_access(self.document.id, 999999)

    def test_should_create_a_pending_access_request(self):
        result = request_document_access(
            self.document.id, self.requester.id, justification="Preciso revisar o projeto"
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["status"], "PENDING")
        access = DocumentAccess.objects.get(document=self.document, user=self.requester)
        self.assertEqual(access.justification, "Preciso revisar o projeto")
        self.assertIsNotNone(access.requested_at)

    def test_should_not_duplicate_an_existing_access_request(self):
        DocumentAccess.objects.create(
            document=self.document,
            user=self.requester,
            status=AccessStatus.PENDING,
            requested_at=timezone.now(),
        )

        result = request_document_access(self.document.id, self.requester.id)

        self.assertFalse(result["created"])
        self.assertEqual(
            DocumentAccess.objects.filter(document=self.document, user=self.requester).count(), 1
        )


class DocumentDetailViewTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible3@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-300",
            title="Documento view",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.responsible,
            auditor=self.responsible,
            audited_at=timezone.now(),
        )
        self.client = Client()

    def test_should_return_200_with_document_metadata(self):
        response = self.client.get(f"/documents/{self.document.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], "DOC-300")

    def test_should_return_404_for_missing_document(self):
        response = self.client.get("/documents/999999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "DocumentNotFound"})

    def test_should_return_404_for_non_numeric_id(self):
        response = self.client.get("/documents/not-a-number")

        self.assertEqual(response.status_code, 404)


class RequestAccessViewTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ENG", name="Engenharia")
        self.discipline = Discipline.objects.create(code="CIV", name="Civil")
        self.project = Project.objects.create(code="PRJ", name="Projeto")
        self.document_type = DocumentType.objects.create(code="PDF", name="Relatório")
        self.responsible = User.objects.create_user(
            email="responsible4@example.com",
            password="test-password",
            name="Responsible",
            area=self.area,
        )
        self.requester = User.objects.create_user(
            email="requester2@example.com",
            password="test-password",
            name="Requester",
            area=self.area,
        )
        self.document = Document.objects.create(
            code="DOC-400",
            title="Documento acesso",
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            responsible=self.responsible,
        )
        self.client = Client()

    def test_should_return_201_when_access_request_is_created(self):
        response = self.client.post(
            f"/documents/{self.document.id}/request-access",
            data={"user_id": self.requester.id, "justification": "Preciso acessar"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "PENDING")

    def test_should_return_404_for_missing_document(self):
        response = self.client.post(
            "/documents/999999/request-access",
            data={"user_id": self.requester.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_should_return_400_when_user_id_is_missing(self):
        response = self.client.post(
            f"/documents/{self.document.id}/request-access",
            data={},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
