from django.test import TestCase

from core.models import AccessGroup, AccessGroupScope, Area, ConfidentialityLevel, User


class AccessGroupOptionsTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="QUA", name="Qualidade")
        self.user = User.objects.create_user(
            email="ana@example.com", password="secret", name="Ana", area=self.area
        )
        self.active = self._group("Qualidade — sigiloso", True)
        self._group("Qualidade — antigo", False, level=ConfidentialityLevel.SECRET)

    def _group(self, name, active, level=ConfidentialityLevel.CONFIDENTIAL):
        return AccessGroup.objects.create(
            name=name,
            scope=AccessGroupScope.AREA,
            area=self.area,
            secrecy_level_id=level,
            active=active,
            created_by=self.user,
        )

    def test_should_require_authentication(self):
        self.assertEqual(self.client.get("/access-groups").status_code, 401)

    def test_should_list_only_active_groups_for_any_authenticated_user(self):
        self.client.force_login(self.user)

        response = self.client.get("/access-groups")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {
                    "id": self.active.id,
                    "name": "Qualidade — sigiloso",
                    "scope": "AREA",
                    "area": "QUA",
                    "secrecy_level": "CONFIDENTIAL",
                }
            ],
        )

    def test_should_reject_other_methods(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.post("/access-groups").status_code, 405)
