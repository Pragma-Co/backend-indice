from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Area,
    Discipline,
    Document,
    DocumentAccess,
    DocumentType,
    Notification,
    NotificationType,
    Project,
    Revision,
    RevisionStatus,
    Role,
    SavedDocument,
    User,
)
from core.services.access_request_exceptions import AccessRequestAlreadyDecidedError
from core.services.access_request_service import decide_access_request
from core.services.notification_exceptions import NotificationNotFoundError
from core.services.notification_service import (
    mark_all_notifications_as_read,
    mark_notification_as_read,
    notify_access_decided,
    notify_revision_published,
)
from core.services.revision_review_service import decide_revision


class NotificationFixtureMixin:
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.other_area = Area.objects.create(acronym="QUA", name="Qualidade")
        self.author = self._user("author@example.com", "Author")
        self.reviewer = self._user("reviewer@example.com", "Reviewer", role=Role.AUDITOR)
        self.reader = self._user("reader@example.com", "Reader")
        self.other_reader = self._user("other@example.com", "Other Reader")
        self.project = Project.objects.create(code="AK-2100", name="Fuselagem")
        self.discipline = Discipline.objects.create(code="EST", name="Estruturas")
        self.document_type = DocumentType.objects.create(code="DWG", name="Desenho")
        self.document = self._document("AK-2100-EST-DWG-0001", "Desenho da caverna 14")
        self._revision(self.document, 1, RevisionStatus.APPROVED)
        self.pending = self._revision(self.document, 2, RevisionStatus.PENDING)

    def _user(self, email, name, area=None, role=Role.VIEWER, is_active=True):
        return User.objects.create_user(
            email=email,
            password="secret",
            name=name,
            area=area or self.area,
            role=role,
            is_active=is_active,
        )

    def _document(self, code, title, confidentiality_level="PUBLIC"):
        return Document.objects.create(
            code=code,
            title=title,
            project=self.project,
            discipline=self.discipline,
            document_type=self.document_type,
            confidentiality_level=confidentiality_level,
            responsible=self.author,
            created_by=self.author,
        )

    def _revision(self, document, version, status):
        decided = status != RevisionStatus.PENDING
        return Revision.objects.create(
            document=document,
            version=version,
            status=status,
            change_description="Atualiza a furação da caverna 14",
            author=self.author,
            auditor=self.reviewer if decided else None,
            audited_at=timezone.now() if decided else None,
        )

    def _access_request(self, user, document=None):
        return DocumentAccess.objects.create(
            document=document or self.document,
            user=user,
            justification="Preciso consultar o desenho para o ensaio",
            requested_at=timezone.now(),
        )

    def _notification(self, recipient, read_at=None, created_at=None, document=None):
        notification = Notification.objects.create(
            recipient=recipient,
            type=NotificationType.DOCUMENT_UPDATED,
            document=document or self.document,
            title="Nova revisão (REV02) publicada para o documento Desenho da caverna 14.",
            read_at=read_at,
        )
        if created_at is not None:
            Notification.objects.filter(pk=notification.pk).update(created_at=created_at)
            notification.refresh_from_db()
        return notification


class RevisionPublishedTriggerTests(NotificationFixtureMixin, TestCase):
    def test_should_notify_every_user_who_saved_the_document_when_a_revision_is_approved(self):
        SavedDocument.objects.create(user=self.reader, document=self.document)
        SavedDocument.objects.create(user=self.other_reader, document=self.document)

        decide_revision(self.pending.pk, self.reviewer, {"decision": "APPROVED"})

        notifications = Notification.objects.order_by("recipient_id")
        self.assertEqual(
            [item.recipient for item in notifications], [self.reader, self.other_reader]
        )
        self.assertTrue(
            all(item.type == NotificationType.DOCUMENT_UPDATED for item in notifications)
        )
        self.assertEqual(
            notifications[0].title,
            "Nova revisão (REV02) publicada para o documento Desenho da caverna 14.",
        )
        self.assertEqual(notifications[0].document, self.document)
        self.assertIsNone(notifications[0].read_at)

    def test_should_not_notify_anyone_when_the_revision_is_rejected(self):
        SavedDocument.objects.create(user=self.reader, document=self.document)

        decide_revision(
            self.pending.pk,
            self.reviewer,
            {"decision": "REJECTED", "justification": "Furação diverge do ensaio aprovado"},
        )

        self.assertFalse(Notification.objects.exists())

    def test_should_not_notify_users_who_did_not_save_the_document(self):
        other_document = self._document("AK-2100-EST-DWG-0002", "Desenho da caverna 15")
        SavedDocument.objects.create(user=self.reader, document=other_document)

        decide_revision(self.pending.pk, self.reviewer, {"decision": "APPROVED"})

        self.assertFalse(Notification.objects.exists())

    def test_should_not_notify_inactive_users(self):
        inactive = self._user("inactive@example.com", "Inactive", is_active=False)
        SavedDocument.objects.create(user=inactive, document=self.document)

        decide_revision(self.pending.pk, self.reviewer, {"decision": "APPROVED"})

        self.assertFalse(Notification.objects.exists())

    def test_should_not_notify_savers_who_can_no_longer_see_the_document(self):
        confidential = self._document("AK-2100-EST-DWG-0003", "Desenho sigiloso", "CONFIDENTIAL")
        self._revision(confidential, 1, RevisionStatus.APPROVED)
        pending = self._revision(confidential, 2, RevisionStatus.PENDING)
        outsider = self._user("outsider@example.com", "Outsider", area=self.other_area)
        SavedDocument.objects.create(user=outsider, document=confidential)

        decide_revision(pending.pk, self.reviewer, {"decision": "APPROVED"})

        self.assertFalse(Notification.objects.exists())

    def test_should_not_notify_the_user_who_published_the_revision(self):
        SavedDocument.objects.create(user=self.reviewer, document=self.document)
        self.pending.status = RevisionStatus.APPROVED

        created = notify_revision_published(self.pending, actor=self.reviewer)

        self.assertEqual(created, [])


class AccessDecisionTriggerTests(NotificationFixtureMixin, TestCase):
    def test_should_notify_the_requester_when_the_access_request_is_approved(self):
        access = self._access_request(self.reader)

        decide_access_request(access.pk, self.author, {"decision": "APPROVED"})

        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.reader)
        self.assertEqual(notification.type, NotificationType.ACCESS_APPROVED)
        self.assertEqual(notification.document, self.document)
        self.assertEqual(
            notification.title,
            "Seu pedido de acesso ao documento Desenho da caverna 14 foi aprovado.",
        )

    def test_should_notify_the_requester_when_the_access_request_is_rejected(self):
        access = self._access_request(self.reader)

        decide_access_request(access.pk, self.author, {"decision": "REJECTED"})

        notification = Notification.objects.get()
        self.assertEqual(notification.recipient, self.reader)
        self.assertEqual(notification.type, NotificationType.ACCESS_REJECTED)
        self.assertEqual(
            notification.title,
            "Seu pedido de acesso ao documento Desenho da caverna 14 foi recusado.",
        )

    def test_should_not_notify_again_when_the_decision_fails(self):
        access = self._access_request(self.reader)
        decide_access_request(access.pk, self.author, {"decision": "APPROVED"})

        with self.assertRaises(AccessRequestAlreadyDecidedError):
            decide_access_request(access.pk, self.author, {"decision": "REJECTED"})

        self.assertEqual(Notification.objects.count(), 1)

    def test_should_ignore_a_pending_access(self):
        access = self._access_request(self.reader)

        notification = notify_access_decided(access)

        self.assertIsNone(notification)
        self.assertFalse(Notification.objects.exists())


class NotificationReadStatusTests(NotificationFixtureMixin, TestCase):
    def test_should_mark_the_notification_as_read(self):
        notification = self._notification(self.reader)

        result = mark_notification_as_read(self.reader, notification.pk)

        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertFalse(result.is_new)

    def test_should_keep_the_first_read_time_when_marked_again(self):
        first_read = timezone.now() - timedelta(days=1)
        notification = self._notification(self.reader, read_at=first_read)

        mark_notification_as_read(self.reader, notification.pk)

        notification.refresh_from_db()
        self.assertEqual(notification.read_at, first_read)

    def test_should_not_mark_a_notification_of_another_user(self):
        notification = self._notification(self.other_reader)

        with self.assertRaises(NotificationNotFoundError):
            mark_notification_as_read(self.reader, notification.pk)

        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_should_mark_only_the_unread_notifications_of_the_user(self):
        already_read = timezone.now() - timedelta(days=1)
        self._notification(self.reader)
        self._notification(self.reader)
        read = self._notification(self.reader, read_at=already_read)
        foreign = self._notification(self.other_reader)

        updated = mark_all_notifications_as_read(self.reader)

        read.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(updated, 2)
        self.assertFalse(Notification.objects.filter(recipient=self.reader, read_at=None).exists())
        self.assertEqual(read.read_at, already_read)
        self.assertIsNone(foreign.read_at)


class NotificationViewTests(NotificationFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.reader)

    def test_should_list_the_user_notifications_newest_first(self):
        now = timezone.now()
        older = self._notification(self.reader, read_at=now, created_at=now - timedelta(hours=2))
        newer = self._notification(self.reader, created_at=now - timedelta(minutes=5))
        self._notification(self.other_reader)

        response = self.client.get(reverse("notification-list"))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["unread_count"], 1)
        self.assertEqual([item["id"] for item in body["results"]], [newer.pk, older.pk])
        self.assertEqual(
            body["results"][0],
            {
                "id": newer.pk,
                "type": "DOCUMENT_UPDATED",
                "title": newer.title,
                "document": {
                    "id": self.document.pk,
                    "code": "AK-2100-EST-DWG-0001",
                    "title": "Desenho da caverna 14",
                },
                "is_new": True,
                "created_at": newer.created_at.isoformat(),
                "read_at": None,
            },
        )
        self.assertFalse(body["results"][1]["is_new"])

    def test_should_list_only_unread_notifications_when_filtered(self):
        self._notification(self.reader, read_at=timezone.now())
        unread = self._notification(self.reader)

        response = self.client.get(reverse("notification-list"), {"unread": "true"})

        self.assertEqual([item["id"] for item in response.json()["results"]], [unread.pk])

    def test_should_paginate_the_notifications(self):
        for _ in range(3):
            self._notification(self.reader)

        response = self.client.get(reverse("notification-list"), {"page": 2, "page_size": 2})

        body = response.json()
        self.assertEqual(body["total_pages"], 2)
        self.assertEqual(body["current_page"], 2)
        self.assertEqual(len(body["results"]), 1)

    def test_should_reject_invalid_query_parameters(self):
        response = self.client.get(
            reverse("notification-list"), {"page_size": "500", "unread": "maybe"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"page_size", "unread"})

    def test_should_require_a_session_to_list_notifications(self):
        self.client.logout()

        response = self.client.get(reverse("notification-list"))

        self.assertEqual(response.status_code, 401)

    def test_should_mark_a_notification_as_read_through_the_endpoint(self):
        notification = self._notification(self.reader)

        response = self.client.patch(reverse("notification-read", args=[notification.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_new"])
        self.assertIsNotNone(response.json()["read_at"])

    def test_should_answer_not_found_for_a_notification_of_another_user(self):
        notification = self._notification(self.other_reader)

        response = self.client.patch(reverse("notification-read", args=[notification.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "NotificationNotFound"})

    def test_should_mark_all_notifications_as_read_through_the_endpoint(self):
        self._notification(self.reader)
        self._notification(self.reader)

        response = self.client.patch(reverse("notification-read-all"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updated": 2, "unread_count": 0})

    def test_should_reject_other_methods_on_the_read_endpoints(self):
        notification = self._notification(self.reader)

        read_response = self.client.post(reverse("notification-read", args=[notification.pk]))
        read_all_response = self.client.post(reverse("notification-read-all"))

        self.assertEqual(read_response.status_code, 405)
        self.assertEqual(read_all_response.status_code, 405)

    def test_should_require_the_csrf_token_to_mark_as_read(self):
        notification = self._notification(self.reader)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.reader)

        response = csrf_client.patch(reverse("notification-read", args=[notification.pk]))

        self.assertEqual(response.status_code, 403)
