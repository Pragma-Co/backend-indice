import json

from django.test import Client, TestCase

from core.models import Area, AuditAction, AuditLog, User
from core.services.excluded_identifier_service import (
    is_identifier_excluded,
    store_excluded_identifier,
)


class UserMeViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.area = Area.objects.create(acronym="USR", name="Usuários")
        self.user = User.objects.create_user(
            email="titular@example.com",
            password="secret",
            name="Titular",
            area=self.area,
        )
        self.client.force_login(self.user)

    def _put(self, payload):
        return self.client.put(
            "/users/me",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_get_returns_only_the_authenticated_users_personal_data(self):
        response = self.client.get("/users/me?user_id=999999")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.pk)
        self.assertEqual(response.json()["name"], "Titular")
        self.assertEqual(response.json()["email"], "titular@example.com")
        self.assertEqual(response.json()["area"]["acronym"], "USR")
        self.assertNotIn("password", response.json())

    def test_put_updates_only_name_and_email_and_records_audit(self):
        response = self._put({"name": "Nome atualizado", "email": "novo@example.com"})

        self.user.refresh_from_db()
        audit = AuditLog.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.name, "Nome atualizado")
        self.assertEqual(self.user.email, "novo@example.com")
        self.assertEqual(response.json()["role"], self.user.role)
        self.assertEqual(audit.action, AuditAction.UPDATE)
        self.assertEqual(audit.entity, "app_user")
        self.assertEqual(audit.record["event"], "PERSONAL_DATA_UPDATED")

    def test_put_rejects_invalid_payloads_without_changing_the_user(self):
        malformed = self.client.put("/users/me", data="{invalid", content_type="application/json")
        self.assertEqual(malformed.status_code, 400)
        invalid_payloads = [
            [],
            {"name": "Titular"},
            {"name": "Titular", "email": "invalid"},
            {"name": "   ", "email": "titular@example.com"},
            {
                "name": "Titular",
                "email": "titular@example.com",
                "role": "ADMIN",
            },
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self._put(payload)
                self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Titular")
        self.assertEqual(self.user.email, "titular@example.com")
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_post_records_request_deactivates_but_does_not_delete_user(self):
        response = self.client.post("/users/me/request-deletion")

        self.user.refresh_from_db()
        audit = AuditLog.objects.get()
        self.assertEqual(response.status_code, 202)
        self.assertFalse(self.user.is_active)
        self.assertIsNotNone(self.user.deletion_requested_at)
        self.assertEqual(
            response.json()["deletion_requested_at"],
            self.user.deletion_requested_at.isoformat(),
        )
        self.assertEqual(User.objects.filter(pk=self.user.pk).count(), 1)
        self.assertEqual(audit.action, AuditAction.UPDATE)
        self.assertEqual(audit.record["event"], "PERSONAL_DATA_DELETION_REQUESTED")
        self.assertTrue(is_identifier_excluded("titular@example.com"))

    def test_requested_deletion_blocks_recreation_after_user_row_is_removed(self):
        response = self.client.post("/users/me/request-deletion")

        self.assertEqual(response.status_code, 202)

        self.user.delete()

        with self.assertRaises(ValueError):
            User.objects.create_user(
                email="TITULAR@example.com",
                password="secret",
                name="Novo cadastro",
                area=self.area,
            )

    def test_put_rejects_email_already_in_the_exclusion_table(self):
        store_excluded_identifier("blocked@example.com")

        response = self._put({"name": "Titular", "email": "blocked@example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["errors"]["email"],
            "This email address cannot be used for an account.",
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "titular@example.com")

    def test_anonymous_requests_are_rejected_on_every_method(self):
        anonymous_client = Client()

        responses = (
            anonymous_client.get("/users/me"),
            anonymous_client.put("/users/me", data="{}", content_type="application/json"),
            anonymous_client.post("/users/me/request-deletion"),
        )
        for response in responses:
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["error"], "Authentication required.")

    def test_put_requires_a_csrf_token_for_session_authenticated_requests(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.put(
            "/users/me",
            data=json.dumps({"name": "Atualizado", "email": "titular@example.com"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
