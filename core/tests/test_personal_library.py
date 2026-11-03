import json

from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    AccessStatus,
    Area,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    Project,
    Revision,
    RevisionStatus,
    SavedDocument,
    User,
)


class PersonalLibraryViewTests(TestCase):
    endpoint = "/users/me/library"

    def setUp(self):
        self.client = Client()
        self.area = Area.objects.create(acronym="LIB", name="Biblioteca")
        self.owner = User.objects.create_user(
            email="owner@example.com", password="pw", name="Owner", area=self.area
        )
        self.user = User.objects.create_user(
            email="user@example.com", password="pw", name="User", area=self.area
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="pw", name="Other", area=self.area
        )
        self.document = Document.objects.create(
            code="LIB-0001",
            title="Documento protegido",
            description="Descricao que requer acesso aprovado",
            project=Project.objects.create(code="LIB", name="Biblioteca"),
            discipline=Discipline.objects.create(code="GEN", name="Geral"),
            document_type=DocumentType.objects.create(code="DOC", name="Documento"),
            responsible=self.owner,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.document.areas.add(self.area)
        Revision.objects.create(
            document=self.document,
            version=1,
            status=RevisionStatus.APPROVED,
            author=self.owner,
            auditor=self.owner,
            audited_at=timezone.now(),
        )
        DocumentAccess.objects.create(
            document=self.document,
            user=self.user,
            status=AccessStatus.APPROVED,
            approver=self.owner,
            decided_at=timezone.now(),
        )
        self.client.force_login(self.user)

    def _request(self, method, document_id):
        return getattr(self.client, method)(
            self.endpoint,
            data=json.dumps({"document_id": document_id}),
            content_type="application/json",
        )

    def test_authenticated_user_can_save_list_and_remove_own_document(self):
        saved = self._request("post", self.document.id)
        listed = self.client.get(self.endpoint)
        removed = self._request("delete", self.document.id)

        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json(), {"document_id": self.document.id, "saved": True})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        item = listed.json()["results"][0]
        self.assertEqual(item["id"], self.document.id)
        self.assertNotIn("files", item)
        self.assertNotIn("storage_path", item)
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(
            SavedDocument.objects.filter(user=self.user, document=self.document).exists()
        )

    def test_user_cannot_save_a_document_without_approved_access(self):
        self.client.force_login(self.other_user)

        response = self._request("post", self.document.id)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SavedDocument.objects.filter(user=self.other_user).exists())

    def test_user_cannot_remove_another_users_saved_document(self):
        SavedDocument.objects.create(user=self.other_user, document=self.document)

        response = self._request("delete", self.document.id)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            SavedDocument.objects.filter(user=self.other_user, document=self.document).exists()
        )

    def test_anonymous_requests_are_rejected(self):
        anonymous_client = Client()

        for response in (
            anonymous_client.get(self.endpoint),
            anonymous_client.post(self.endpoint, data="{}", content_type="application/json"),
            anonymous_client.delete(self.endpoint, data="{}", content_type="application/json"),
        ):
            self.assertEqual(response.status_code, 401)
