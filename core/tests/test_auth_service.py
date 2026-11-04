from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from core.models import Area, AuditAction, AuditLog, User
from core.services.auth_exceptions import InvalidCredentialsError
from core.services.auth_service import sign_in

PASSWORD = "Correct-Horse-42"


class SignInTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="titular@example.com", password=PASSWORD, name="Titular", area=self.area
        )

    def _request(self):
        request = RequestFactory().post(
            "/auth/login", REMOTE_ADDR="198.51.100.20", HTTP_USER_AGENT="Firefox"
        )
        request.session = SessionStore()
        request.user = AnonymousUser()
        return request

    def test_should_store_the_password_as_a_pbkdf2_hash(self):
        stored = User.objects.get(pk=self.user.pk).password

        is_hashed = stored.startswith("pbkdf2_sha256$")

        self.assertTrue(is_hashed)
        self.assertNotEqual(stored, PASSWORD)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(PASSWORD))

    def test_should_authenticate_valid_credentials_and_open_the_session(self):
        request = self._request()

        user = sign_in(request, " titular@example.com ", PASSWORD)

        self.assertEqual(user, self.user)
        self.assertEqual(request.user, self.user)
        self.assertEqual(request.session[SESSION_KEY], str(self.user.pk))

    def test_should_refuse_a_wrong_password(self):
        request = self._request()

        with self.assertRaises(InvalidCredentialsError):
            sign_in(request, "titular@example.com", "wrong-password")

        self.assertNotIn(SESSION_KEY, request.session)

    def test_should_refuse_an_unknown_email(self):
        request = self._request()

        with self.assertRaises(InvalidCredentialsError):
            sign_in(request, "nobody@example.com", PASSWORD)

        self.assertNotIn(SESSION_KEY, request.session)

    def test_should_refuse_an_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        request = self._request()

        with self.assertRaises(InvalidCredentialsError):
            sign_in(request, "titular@example.com", PASSWORD)

        self.assertNotIn(SESSION_KEY, request.session)

    def test_should_refuse_a_user_with_an_unusable_password(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        request = self._request()

        with self.assertRaises(InvalidCredentialsError):
            sign_in(request, "titular@example.com", PASSWORD)

        self.assertNotIn(SESSION_KEY, request.session)

    def test_should_write_the_login_audit_entry(self):
        request = self._request()

        sign_in(request, "titular@example.com", PASSWORD)

        entry = AuditLog.objects.get(action=AuditAction.LOGIN)
        self.assertEqual(entry.user, self.user)
        self.assertEqual(entry.entity, "app_user")
        self.assertEqual(entry.entity_id, self.user.pk)
        self.assertEqual(entry.ip_address, "198.51.100.20")
        self.assertEqual(entry.record["user_agent"], "Firefox")
        self.assertTrue(entry.record["actor"]["authenticated"])

    def test_should_not_write_an_audit_entry_for_refused_credentials(self):
        request = self._request()

        with self.assertRaises(InvalidCredentialsError):
            sign_in(request, "titular@example.com", "wrong-password")

        self.assertFalse(AuditLog.objects.filter(action=AuditAction.LOGIN).exists())
