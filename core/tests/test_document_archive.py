import json

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    AuditAction,
    AuditLog,
    Discipline,
    Document,
    DocumentType,
    File,
    Project,
    Revision,
    RevisionStatus,
    Role,
    User,
)
from core.services.document_archive_service import (
    archive_document,
    can_archive_document,
    restore_document,
)
from core.services.documents_exceptions import ArchivePermissionDeniedError, DocumentNotFoundError


class DocumentArchiveFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.other_area = Area.objects.create(acronym="MFG", name="Manufatura e Montagem")
        self.manager = self._user("manager@example.com", "Manager", Role.AUDITOR, self.area)
        self.admin = self._user("admin@example.com", "Admin", Role.ADMIN, self.area)
        self.other_manager = self._user(
            "other.manager@example.com", "Other Manager", Role.AUDITOR, self.other_area
        )
        self.author = self._user("author@example.com", "Author", Role.AUTHOR, self.area)
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.document = self._document("AK-2100-EST-DWG-0001", self.area)
        self.current = self._revision(self.document, 1, RevisionStatus.APPROVED)
        self.pending = self._revision(self.document, 2, RevisionStatus.PENDING)
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

    def _revision(self, document, version, status):
        decided = status != RevisionStatus.PENDING
        revision = Revision.objects.create(
            document=document,
            version=version,
            status=status,
            change_description="Atualiza a furação da caverna 14",
            author=self.author,
            auditor=self.manager if decided else None,
            audited_at=timezone.now() if decided else None,
        )
        File.objects.create(
            revision=revision,
            original_name=f"{document.code}-v{version}.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size_bytes=100,
            sha256=f"{document.pk:032x}{version:032x}",
            storage_path=f"{document.code}/v{version}.pdf",
        )
        return revision

    def _delete(self, document_id, client=None):
        return (client or self.client).delete(reverse("document-detail", args=[document_id]))


class ArchiveDocumentServiceTests(DocumentArchiveFixtureMixin, TestCase):
    def test_should_archive_the_document_for_a_manager_of_one_of_its_areas(self):
        before = timezone.now()

        document = archive_document(self.document.pk, self.manager)

        self.document.refresh_from_db()
        self.assertGreaterEqual(document.archived_at, before)
        self.assertEqual(self.document.archived_at, document.archived_at)
        self.assertEqual(self.document.archived_by, self.manager)
        self.assertEqual(self.document.updated_by, self.manager)
        self.assertTrue(Document.objects.filter(pk=self.document.pk).exists())

    def test_should_allow_an_administrator_of_the_area(self):
        document = archive_document(self.document.pk, self.admin)

        self.assertEqual(document.archived_by, self.admin)

    def test_should_refuse_a_manager_of_another_area(self):
        with self.assertRaises(ArchivePermissionDeniedError):
            archive_document(self.document.pk, self.other_manager)

        self.document.refresh_from_db()
        self.assertIsNone(self.document.archived_at)
        self.assertIsNone(self.document.archived_by)

    def test_should_refuse_users_without_manager_role_even_in_the_same_area(self):
        with self.assertRaises(ArchivePermissionDeniedError):
            archive_document(self.document.pk, self.author)

        self.document.refresh_from_db()
        self.assertIsNone(self.document.archived_at)

    def test_should_recognize_the_manager_only_for_documents_of_their_area(self):
        other_document = self._document("AK-2100-EST-DWG-0002", self.other_area)

        decisions = (
            can_archive_document(self.document, self.manager),
            can_archive_document(other_document, self.manager),
            can_archive_document(other_document, self.other_manager),
            can_archive_document(self.document, None),
        )

        self.assertEqual(decisions, (True, False, True, False))

    def test_should_raise_not_found_when_the_document_type_is_inactive(self):
        self.document_type.active = False
        self.document_type.save(update_fields=["active"])

        with self.assertRaises(DocumentNotFoundError):
            archive_document(self.document.pk, self.manager)

        self.document.refresh_from_db()
        self.assertIsNone(self.document.archived_at)

    def test_should_raise_not_found_for_unknown_or_already_archived_documents(self):
        archive_document(self.document.pk, self.manager)

        with self.assertRaises(DocumentNotFoundError):
            archive_document(self.document.pk, self.manager)
        with self.assertRaises(DocumentNotFoundError):
            archive_document(999_999, self.manager)

        self.document.refresh_from_db()
        self.assertEqual(self.document.archived_by, self.manager)


class ArchiveDocumentViewTests(DocumentArchiveFixtureMixin, TestCase):
    def test_should_archive_and_record_the_audit_trail(self):
        self.client.force_login(self.manager)

        response = self._delete(self.document.pk)

        self.document.refresh_from_db()
        body = response.json()
        audit = AuditLog.objects.get(entity="document")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["id"], self.document.pk)
        self.assertEqual(body["code"], self.document.code)
        self.assertEqual(body["archived_at"], self.document.archived_at.isoformat())
        self.assertEqual(body["archived_by"], {"id": self.manager.pk, "name": "Manager"})
        self.assertEqual(audit.action, AuditAction.DELETE)
        self.assertEqual(audit.entity_id, self.document.pk)
        self.assertEqual(audit.user, self.manager)
        self.assertEqual(audit.record["event"], "DOCUMENT_ARCHIVED")
        self.assertEqual(audit.record["document_code"], self.document.code)
        self.assertEqual(audit.record["areas"], ["EST"])

    def test_should_require_authentication(self):
        response = self._delete(self.document.pk)

        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})
        self.assertIsNone(self.document.archived_at)

    def test_should_forbid_managers_of_other_areas_and_users_without_manager_role(self):
        for user in (self.other_manager, self.author):
            with self.subTest(user=user.email):
                self.client.force_login(user)

                response = self._delete(self.document.pk)

                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"error": "PermissionDenied"})

        self.document.refresh_from_db()
        self.assertIsNone(self.document.archived_at)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_answer_not_found_for_unknown_and_already_archived_documents(self):
        self.client.force_login(self.manager)
        self._delete(self.document.pk)

        responses = (self._delete(self.document.pk), self._delete(999_999))

        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"error": "DocumentNotFound"})
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_should_require_a_csrf_token_for_session_authenticated_requests(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)

        response = self._delete(self.document.pk, client=client)

        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.document.archived_at)

    def test_should_keep_serving_the_detail_on_get_and_reject_other_methods(self):
        url = reverse("document-detail", args=[self.document.pk])
        self.client.force_login(self.manager)

        detail = self.client.get(url)
        rejected = (self.client.post(url), self.client.put(url), self.client.patch(url))

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["code"], self.document.code)
        self.assertEqual([response.status_code for response in rejected], [405, 405, 405])


class ArchivedDocumentVisibilityTests(DocumentArchiveFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.visible = self._document("AK-2100-EST-DWG-0002", self.area)
        self._revision(self.visible, 1, RevisionStatus.APPROVED)
        archive_document(self.document.pk, self.manager)

    def test_should_hide_archived_documents_from_the_listing(self):
        response = self.client.get(reverse("document-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual([item["code"] for item in response.json()["results"]], [self.visible.code])

    def test_should_answer_not_found_for_the_detail_of_an_archived_document(self):
        self.client.force_login(self.author)

        response = self.client.get(reverse("document-detail", args=[self.document.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "DocumentNotFound"})

    def test_should_refuse_new_revisions_for_an_archived_document(self):
        response = self.client.post(
            reverse("document-revision-create", args=[self.document.pk]),
            data=json.dumps(
                {
                    "temp_file_ids": ["any-temp-file"],
                    "change_description": "Atualiza a furação da caverna 14",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "DocumentNotFound"})
        self.assertEqual(self.document.revisions.count(), 2)

    def test_should_hide_pending_revisions_of_archived_documents_from_the_manager_queue(self):
        self.client.force_login(self.manager)

        queue = self.client.get(reverse("manager-pending-revisions"))
        decision = self.client.post(
            reverse("manager-revision-decision", args=[self.pending.pk]),
            data=json.dumps({"decision": "APPROVED"}),
            content_type="application/json",
        )

        self.pending.refresh_from_db()
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.json()["results"], [])
        self.assertEqual(decision.status_code, 404)
        self.assertEqual(decision.json(), {"error": "RevisionNotFound"})
        self.assertEqual(self.pending.status, RevisionStatus.PENDING)

    def test_should_refuse_access_requests_and_file_views_for_an_archived_document(self):
        file = self.current.files.get()

        access = self.client.post(
            reverse("document-request-access", args=[self.document.pk]),
            data=json.dumps({"user_id": self.other_manager.pk, "justification": "Preciso"}),
            content_type="application/json",
        )
        view = self.client.get(
            reverse("document-file-view", args=[file.pk]), {"user_id": self.author.pk}
        )

        self.assertEqual(access.status_code, 404)
        self.assertEqual(access.json(), {"error": "DocumentNotFound"})
        self.assertEqual(view.status_code, 404)
        self.assertEqual(view.json(), {"error": "FileNotFound"})


class ArchivedDocumentsListViewTests(DocumentArchiveFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("document-archived-list")
        self.other_document = self._document("AK-2100-EST-DWG-0002", self.other_area)
        archive_document(self.document.pk, self.manager)
        archive_document(self.other_document.pk, self.other_manager)
        self.document.refresh_from_db()

    def test_should_list_only_the_archived_documents_of_the_managers_area(self):
        self._document("AK-2100-EST-DWG-0003", self.area)
        self.client.force_login(self.manager)

        response = self.client.get(self.url)

        body = response.json()
        item = body["results"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual([entry["code"] for entry in body["results"]], [self.document.code])
        self.assertEqual(item["archived_at"], self.document.archived_at.isoformat())
        self.assertEqual(item["archived_by"], {"id": self.manager.pk, "name": "Manager"})
        self.assertEqual(item["status"], RevisionStatus.PENDING)

    def test_should_accept_the_same_filters_as_the_general_listing(self):
        self.client.force_login(self.manager)

        matching = self.client.get(self.url, {"q": "0001"})
        empty = self.client.get(self.url, {"tipo": "MEM"})
        invalid = self.client.get(self.url, {"page": "0"})

        self.assertEqual(
            [entry["code"] for entry in matching.json()["results"]], [self.document.code]
        )
        self.assertEqual(empty.json()["count"], 0)
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("page", invalid.json()["errors"])

    def test_should_require_authentication_and_the_manager_role(self):
        anonymous = self.client.get(self.url)
        self.client.force_login(self.author)
        forbidden = self.client.get(self.url)

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.json(), {"error": "AuthenticationRequired"})
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json(), {"error": "PermissionDenied"})

    def test_should_keep_archived_documents_out_of_the_general_listing(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("document-list"))

        self.assertEqual(response.json()["count"], 0)

    def test_should_only_accept_get(self):
        self.client.force_login(self.manager)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 405)


class RestoreDocumentServiceTests(DocumentArchiveFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        archive_document(self.document.pk, self.manager)

    def test_should_restore_the_document_for_a_manager_of_one_of_its_areas(self):
        document = restore_document(self.document.pk, self.admin)

        self.document.refresh_from_db()
        self.assertIsNone(document.archived_at)
        self.assertIsNone(self.document.archived_at)
        self.assertIsNone(self.document.archived_by)
        self.assertEqual(self.document.updated_by, self.admin)

    def test_should_refuse_managers_of_other_areas_and_users_without_manager_role(self):
        for user in (self.other_manager, self.author):
            with self.subTest(user=user.email), self.assertRaises(ArchivePermissionDeniedError):
                restore_document(self.document.pk, user)

        self.document.refresh_from_db()
        self.assertEqual(self.document.archived_by, self.manager)

    def test_should_raise_not_found_for_unknown_or_active_documents(self):
        active = self._document("AK-2100-EST-DWG-0002", self.area)

        with self.assertRaises(DocumentNotFoundError):
            restore_document(active.pk, self.manager)
        with self.assertRaises(DocumentNotFoundError):
            restore_document(999_999, self.manager)


class RestoreDocumentViewTests(DocumentArchiveFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        archive_document(self.document.pk, self.manager)
        self.url = reverse("document-restore", args=[self.document.pk])

    def test_should_restore_and_record_the_audit_trail(self):
        self.client.force_login(self.manager)

        response = self.client.post(self.url)

        self.document.refresh_from_db()
        audit = AuditLog.objects.get(entity="document")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.document.pk,
                "code": self.document.code,
                "archived_at": None,
                "restored_by": {"id": self.manager.pk, "name": "Manager"},
            },
        )
        self.assertIsNone(self.document.archived_at)
        self.assertIsNone(self.document.archived_by)
        self.assertEqual(audit.action, AuditAction.UPDATE)
        self.assertEqual(audit.entity_id, self.document.pk)
        self.assertEqual(audit.user, self.manager)
        self.assertEqual(audit.record["event"], "DOCUMENT_RESTORED")
        self.assertEqual(audit.record["areas"], ["EST"])

    def test_should_bring_the_document_back_to_the_general_listing_and_detail(self):
        self.client.force_login(self.manager)
        self.client.post(self.url)

        listing = self.client.get(reverse("document-list"))
        detail = self.client.get(reverse("document-detail", args=[self.document.pk]))
        archived = self.client.get(reverse("document-archived-list"))

        self.assertEqual(
            [entry["code"] for entry in listing.json()["results"]], [self.document.code]
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(archived.json()["count"], 0)

    def test_should_require_authentication(self):
        response = self.client.post(self.url)

        self.document.refresh_from_db()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})
        self.assertIsNotNone(self.document.archived_at)

    def test_should_forbid_managers_of_other_areas_and_users_without_manager_role(self):
        for user in (self.other_manager, self.author):
            with self.subTest(user=user.email):
                self.client.force_login(user)

                response = self.client.post(self.url)

                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"error": "PermissionDenied"})

        self.document.refresh_from_db()
        self.assertIsNotNone(self.document.archived_at)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_should_answer_not_found_for_active_and_unknown_documents(self):
        self.client.force_login(self.manager)
        self.client.post(self.url)

        responses = (
            self.client.post(self.url),
            self.client.post(reverse("document-restore", args=[999_999])),
        )

        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"error": "DocumentNotFound"})

    def test_should_require_a_csrf_token_and_reject_other_methods(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)

        without_token = client.post(self.url)
        wrong_method = client.get(self.url)

        self.document.refresh_from_db()
        self.assertEqual(without_token.status_code, 403)
        self.assertEqual(wrong_method.status_code, 405)
        self.assertIsNotNone(self.document.archived_at)
