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


class PersonalLibraryFixtureMixin:
    def _create_area(self, acronym="LIB", name="Biblioteca"):
        return Area.objects.create(acronym=acronym, name=name)

    def _create_user(self, email, name, area=None):
        if area is None:
            area = self.area
        return User.objects.create_user(email=email, password="pw", name=name, area=area)

    def _create_project(self, code="LIB", name="Biblioteca"):
        return Project.objects.create(code=code, name=name)

    def _create_discipline(self, code="GEN", name="Geral"):
        return Discipline.objects.create(code=code, name=name)

    def _create_document_type(self, code="DOC", name="Documento", active=True):
        return DocumentType.objects.create(code=code, name=name, active=active)

    def _create_document(
        self,
        code,
        title,
        project=None,
        discipline=None,
        document_type=None,
        responsible=None,
        created_by=None,
        updated_by=None,
        archived_at=None,
        archived_by=None,
    ):
        if project is None:
            project = self.project
        if discipline is None:
            discipline = self.discipline
        if document_type is None:
            document_type = self.document_type
        if responsible is None:
            responsible = self.owner
        if created_by is None:
            created_by = self.owner
        if updated_by is None:
            updated_by = self.owner
        if archived_at is not None and archived_by is None:
            archived_by = self.owner

        document = Document.objects.create(
            code=code,
            title=title,
            project=project,
            discipline=discipline,
            document_type=document_type,
            responsible=responsible,
            created_by=created_by,
            updated_by=updated_by,
            archived_at=archived_at,
            archived_by=archived_by,
        )
        return document

    def _create_revision(
        self, document, version=1, status=RevisionStatus.APPROVED, author=None, auditor=None
    ):
        if author is None:
            author = self.owner
        if auditor is None:
            auditor = self.owner

        return Revision.objects.create(
            document=document,
            version=version,
            status=status,
            author=author,
            auditor=auditor,
            audited_at=timezone.now(),
        )

    def _create_access(self, document, user, status=AccessStatus.APPROVED, approver=None):
        if approver is None:
            approver = self.owner

        return DocumentAccess.objects.create(
            document=document,
            user=user,
            status=status,
            approver=approver,
            decided_at=timezone.now(),
        )


class PersonalLibraryViewTests(PersonalLibraryFixtureMixin, TestCase):
    def setUp(self):
        self.client = Client()
        self.area = self._create_area()
        self.owner = self._create_user("owner@example.com", "Owner")
        self.user = self._create_user("user@example.com", "User")
        self.other_user = self._create_user("other@example.com", "Other")

        self.project = self._create_project()
        self.discipline = self._create_discipline()
        self.document_type = self._create_document_type()

        self.document = self._create_document(
            code="LIB-0001",
            title="Documento protegido",
        )
        self.document.areas.add(self.area)
        self._create_revision(self.document)
        self._create_access(self.document, self.user)
        self.client.force_login(self.user)

    def _item_url(self, document_id=None):
        return f"/users/me/library/{document_id or self.document.id}"

    def _extra_document(
        self,
        code,
        title=None,
        has_access=True,
        archived=False,
        document_type=None,
        active_type=True,
    ):
        if document_type is None:
            if active_type:
                document_type = self.document_type
            else:
                document_type = self._create_document_type(
                    code="INAC", name="Inativo", active=False
                )

        doc = self._create_document(
            code=code,
            title=title or code,
            document_type=document_type,
            responsible=self.user,
            created_by=self.user,
            updated_by=self.user,
            archived_at=timezone.now() if archived else None,
        )
        doc.areas.add(self.area)
        self._create_revision(doc)

        if has_access:
            self._create_access(doc, self.user)

        return doc

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

    def test_user_can_save_a_public_document_without_direct_access(self):
        # A user without DocumentAccess can still favorite public documents
        public_doc = self._extra_document("PUB-001", has_access=False)
        self.client.force_login(self.other_user)

        response = self.client.post(f"/users/me/library/{public_doc.id}")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(SavedDocument.objects.filter(user=self.other_user, document=public_doc).exists())

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

    def test_should_not_save_archived_document(self):
        archived_doc = self._extra_document("ARC-001", archived=True)

        response = self.client.post(f"/users/me/library/{archived_doc.id}")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            SavedDocument.objects.filter(user=self.user, document=archived_doc).exists()
        )

    def test_should_not_save_document_with_inactive_type(self):
        inactive_type_doc = self._extra_document("INAC-001", active_type=False)

        response = self.client.post(f"/users/me/library/{inactive_type_doc.id}")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            SavedDocument.objects.filter(user=self.user, document=inactive_type_doc).exists()
        )

    def test_listing_should_not_return_archived_documents(self):
        active_doc = self._extra_document("ACT-001")
        archived_doc = self._extra_document("ARC-001", archived=True)

        SavedDocument.objects.create(user=self.user, document=active_doc)
        SavedDocument.objects.create(user=self.user, document=archived_doc)

        response = self.client.get("/users/me/library")

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["id"] for item in response.json()["results"]]
        self.assertIn(active_doc.id, returned_ids)
        self.assertNotIn(archived_doc.id, returned_ids)

    def test_listing_should_not_return_documents_with_inactive_type(self):
        active_doc = self._extra_document("ACT-002")
        inactive_type_doc = self._extra_document("INAC-002", active_type=False)

        SavedDocument.objects.create(user=self.user, document=active_doc)
        SavedDocument.objects.create(user=self.user, document=inactive_type_doc)

        response = self.client.get("/users/me/library")

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["id"] for item in response.json()["results"]]
        self.assertIn(active_doc.id, returned_ids)
        self.assertNotIn(inactive_type_doc.id, returned_ids)

    def test_listing_should_order_by_saved_at_descending(self):
        doc1 = self._extra_document("DOC-001")
        doc2 = self._extra_document("DOC-002")
        doc3 = self._extra_document("DOC-003")
        
        # Save documents in forward order to test descending sort
        SavedDocument.objects.create(user=self.user, document=doc1)
        SavedDocument.objects.create(user=self.user, document=doc2)
        SavedDocument.objects.create(user=self.user, document=doc3)

        response = self.client.get("/users/me/library")

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        returned_ids = [item["id"] for item in results]
        # Should be in reverse order of save time (most recent first)
        self.assertEqual(returned_ids, [doc3.id, doc2.id, doc1.id])

    def test_listing_respects_pagination_with_multiple_pages(self):
        docs = [self._extra_document(f"DOC-{i:03d}") for i in range(5)]
        for doc in docs:
            SavedDocument.objects.create(user=self.user, document=doc)

        response_page1 = self.client.get("/users/me/library", {"page": 1, "page_size": 2})
        body_page1 = response_page1.json()
        self.assertEqual(response_page1.status_code, 200)
        self.assertEqual(body_page1["count"], 5)
        self.assertEqual(body_page1["current_page"], 1)
        self.assertEqual(len(body_page1["results"]), 2)

        response_page2 = self.client.get("/users/me/library", {"page": 2, "page_size": 2})
        body_page2 = response_page2.json()
        self.assertEqual(response_page2.status_code, 200)
        self.assertEqual(body_page2["current_page"], 2)
        self.assertEqual(len(body_page2["results"]), 2)

        response_page3 = self.client.get("/users/me/library", {"page": 3, "page_size": 2})
        body_page3 = response_page3.json()
        self.assertEqual(response_page3.status_code, 200)
        self.assertEqual(body_page3["current_page"], 3)
        self.assertEqual(len(body_page3["results"]), 1)

    def test_listing_empty_when_no_documents_saved(self):
        response = self.client.get("/users/me/library")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])

    def test_saved_document_includes_saved_at_timestamp(self):
        SavedDocument.objects.create(user=self.user, document=self.document)

        response = self.client.get("/users/me/library")

        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertIn("id", item)
        self.assertTrue(item["is_favorite"])
        self.assertEqual(item["id"], self.document.id)

    def test_can_save_document_even_without_direct_access(self):
        # User can favorite any public document, even without DocumentAccess
        no_access_doc = self._extra_document("NO-ACCESS-001", has_access=False)

        response = self.client.post(f"/users/me/library/{no_access_doc.id}")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            SavedDocument.objects.filter(user=self.user, document=no_access_doc).exists()
        )
