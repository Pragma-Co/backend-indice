from django.test import TestCase

from core.models import Area, Role, User


class ManagerAreaUsersTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Structures")
        self.other_area = Area.objects.create(acronym="MFG", name="Manufacturing")
        self.manager = User.objects.create_user(
            email="manager@example.com",
            password="secret",
            name="Manager",
            role=Role.AUDITOR,
            area=self.area,
        )
        self.client.force_login(self.manager)

    def test_should_list_only_active_collaborators_of_managers_area(self):
        bruno = User.objects.create_user(
            email="bruno@example.com", password="secret", name="Bruno", area=self.area
        )
        User.objects.create_user(
            email="auditor@example.com",
            password="secret",
            name="Auditor",
            area=self.area,
            role=Role.AUDITOR,
        )
        User.objects.create_user(
            email="admin@example.com",
            password="secret",
            name="Admin",
            area=self.area,
            role=Role.ADMIN,
        )
        ana = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=self.area
        )
        User.objects.create_user(
            email="carla@example.com",
            password="secret",
            name="Carla",
            area=self.area,
            is_active=False,
        )
        User.objects.create_user(
            email="diego@example.com", password="secret", name="Diego", area=self.other_area
        )

        response = self.client.get("/manager/users")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"],
            [
                {"id": ana.id, "name": "Ana", "email": "ana@example.com"},
                {"id": bruno.id, "name": "Bruno", "email": "bruno@example.com"},
            ],
        )

    def test_should_require_authentication(self):
        self.client.logout()

        response = self.client.get("/manager/users")

        self.assertEqual(response.status_code, 401)

    def test_should_deny_users_who_are_not_managers(self):
        viewer = User.objects.create_user(
            email="viewer@example.com",
            password="secret",
            name="Viewer",
            role=Role.VIEWER,
            area=self.area,
        )
        self.client.force_login(viewer)

        response = self.client.get("/manager/users")

        self.assertEqual(response.status_code, 403)

    def test_should_deny_managers_of_inactive_areas(self):
        self.area.active = False
        self.area.save(update_fields=["active"])

        response = self.client.get("/manager/users")

        self.assertEqual(response.status_code, 403)

    def test_should_reject_other_methods(self):
        response = self.client.post("/manager/users")

        self.assertEqual(response.status_code, 405)
