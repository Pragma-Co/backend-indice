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

    def _item_url(self, document_id=None):
        return f"/users/me/library/{document_id or self.document.id}"

    def _extra_document(self, code):
        document = Document.objects.create(
            code=code,
            title=code,
            project=self.document.project,
            discipline=self.document.discipline,
            document_type=self.document.document_type,
            responsible=self.user,
            created_by=self.user,
            updated_by=self.user,
        )
        document.areas.add(self.area)
        return document

    def test_authenticated_user_can_save_list_and_remove_own_document(self):
        saved = self.client.post(self._item_url())
        listed = self.client.get("/users/me/library")
        removed = self.client.delete(self._item_url())

        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json(), {"document_id": self.document.id, "saved": True})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        item = listed.json()["results"][0]
        self.assertEqual(item["id"], self.document.id)
        self.assertTrue(item["is_favorite"])
        self.assertNotIn("files", item)
        self.assertNotIn("storage_path", item)
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(
            SavedDocument.objects.filter(user=self.user, document=self.document).exists()
        )

    def test_saving_twice_is_idempotent(self):
        first = self.client.post(self._item_url())
        second = self.client.post(self._item_url())

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(SavedDocument.objects.filter(user=self.user).count(), 1)

    def test_removing_a_document_that_is_not_saved_is_idempotent(self):
        response = self.client.delete(self._item_url())

        self.assertEqual(response.status_code, 204)

    def test_saving_an_unknown_document_returns_not_found(self):
        response = self.client.post(self._item_url(999999))

        self.assertEqual(response.status_code, 404)

    def test_listing_is_paginated(self):
        for index in range(3):
            document = self._extra_document(f"EX-{index}")
            SavedDocument.objects.create(user=self.user, document=document)

        response = self.client.get("/users/me/library", {"page": 2, "page_size": 2})

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["total_pages"], 2)
        self.assertEqual(body["current_page"], 2)
        self.assertEqual(len(body["results"]), 1)

    def test_listing_only_returns_the_authenticated_users_documents(self):
        SavedDocument.objects.create(user=self.user, document=self.document)
        other_document = self._extra_document("EX-OTHER")
        SavedDocument.objects.create(user=self.other_user, document=other_document)

        response = self.client.get("/users/me/library")

        self.assertEqual([item["id"] for item in response.json()["results"]], [self.document.id])

    def test_document_listing_identifies_the_authenticated_users_favorites(self):
        SavedDocument.objects.create(user=self.user, document=self.document)

        response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["results"][0]["is_favorite"])

    def test_user_cannot_save_a_document_without_approved_access(self):
        self.client.force_login(self.other_user)

        response = self.client.post(self._item_url())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SavedDocument.objects.filter(user=self.other_user).exists())

    def test_user_cannot_remove_another_users_saved_document(self):
        SavedDocument.objects.create(user=self.other_user, document=self.document)

        response = self.client.delete(self._item_url())

        self.assertEqual(response.status_code, 204)
        self.assertTrue(
            SavedDocument.objects.filter(user=self.other_user, document=self.document).exists()
        )

    def test_anonymous_requests_are_rejected(self):
        anonymous_client = Client()

        for response in (
            anonymous_client.get("/users/me/library"),
            anonymous_client.post(self._item_url()),
            anonymous_client.delete(self._item_url()),
        ):
            self.assertEqual(response.status_code, 401)
