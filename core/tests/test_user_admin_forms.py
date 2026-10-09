from django.test import TestCase, override_settings

from core.admin import CoreUserChangeForm, CoreUserCreationForm
from core.models import Area, Role, User
from core.services.excluded_identifier_service import store_excluded_identifier


@override_settings(EXCLUDED_IDENTIFIER_HMAC_KEY="test-only-stable-key")
class UserAdminFormTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="ADM", name="Administração")
        self.user = User.objects.create_user(
            email="existing@example.com",
            password="secret",
            name="Existing User",
            area=self.area,
        )
        store_excluded_identifier("blocked@example.com")

    def test_creation_form_rejects_excluded_email(self):
        form = CoreUserCreationForm(
            data={
                "email": "blocked@example.com",
                "name": "Blocked User",
                "role": Role.VIEWER,
                "area": self.area.pk,
                "password1": "Admin-user-pass-917!x",
                "password2": "Admin-user-pass-917!x",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "This email address cannot be used for an account.",
            form.errors["email"],
        )


    def test_change_form_rejects_excluded_email(self):
        form = CoreUserChangeForm(
            data={
                "email": "blocked@example.com",
                "name": self.user.name,
                "role": self.user.role,
                "area": self.area.pk,
                "is_active": "on",
            },
            instance=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "This email address cannot be used for an account.",
            form.errors["email"],
        )
