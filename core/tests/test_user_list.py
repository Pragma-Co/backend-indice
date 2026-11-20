from django.test import TestCase

from core.models import Area, User


class UserListTests(TestCase):
    def setUp(self):
        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.ana = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=area
        )
        self.bruno = User.objects.create_user(
            email="bruno@example.com", password="secret", name="Bruno", area=area
        )
        self.former = User.objects.create_user(
            email="carla@example.com", password="secret", name="Carla", area=area, is_active=False
        )

    def test_should_require_authentication(self):
        response = self.client.get("/users")

        self.assertEqual(response.status_code, 401)

    def test_should_list_only_active_users_ordered_by_name(self):
        self.client.force_login(self.ana)

        response = self.client.get("/users")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"id": self.ana.id, "name": "Ana", "email": "ana@example.com"},
                {"id": self.bruno.id, "name": "Bruno", "email": "bruno@example.com"},
            ],
        )

    def test_should_reject_other_methods(self):
        self.client.force_login(self.ana)

        response = self.client.post("/users")

        self.assertEqual(response.status_code, 405)
