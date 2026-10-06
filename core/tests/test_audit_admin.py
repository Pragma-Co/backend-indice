from django.test import TestCase
from django.urls import reverse

from core.models import Area, AuditAction, AuditLog, Role, User


class AuditLogAdminTests(TestCase):
    def setUp(self):
        area = Area.objects.create(acronym="AUD", name="Auditoria")
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="secret",
            name="Administradora",
            area=area,
            role=Role.ADMIN,
        )
        self.client.force_login(self.admin_user)
        self.audit_log = AuditLog.objects.create(
            user=self.admin_user,
            action=AuditAction.UPDATE,
            entity="app_user",
            entity_id=self.admin_user.pk,
            record={"event": "PERSONAL_DATA_DELETION_REQUESTED"},
        )

    def test_deletion_request_is_visible_in_read_only_audit_log(self):
        response = self.client.get(reverse("admin:core_auditlog_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Personal data deletion requested")

        detail = self.client.get(
            reverse("admin:core_auditlog_change", args=[self.audit_log.pk])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "PERSONAL_DATA_DELETION_REQUESTED")
        self.assertNotContains(detail, 'name="_save"')
