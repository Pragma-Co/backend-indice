from django.test import TestCase

from core.models import (
    AccessGroup,
    AccessGroupMember,
    AccessGroupScope,
    Area,
    Project,
    Role,
    SecrecyLevel,
    User,
)
from core.services.access_group_management_service import GroupManagementError, create_group


class AccessGroupApiTests(TestCase):
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
        self.level = SecrecyLevel.objects.get(pk="SECRET")
        self.group = AccessGroup.objects.create(
            name="Structures group",
            scope=AccessGroupScope.AREA,
            area=self.area,
            secrecy_level=self.level,
            created_by=self.manager,
        )
        self.other_group = AccessGroup.objects.create(
            name="Manufacturing group",
            scope=AccessGroupScope.AREA,
            area=self.other_area,
            secrecy_level=self.level,
            created_by=self.manager,
        )
        self.client.force_login(self.manager)

    def test_list_only_includes_groups_of_managers_area(self):
        response = self.client.get("/manager/access-groups")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["results"]], [self.group.id])

    def test_create_group_uses_authenticated_area_and_creator(self):
        response = self.client.post(
            "/manager/access-groups",
            {"name": " Confidential team ", "description": "Team", "secrecy_level": "CONFIDENTIAL"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        group = AccessGroup.objects.get(pk=response.json()["id"])
        self.assertEqual(
            (group.name, group.area_id, group.created_by_id),
            ("Confidential team", self.area.id, self.manager.id),
        )
        self.assertEqual(group.scope, AccessGroupScope.AREA)

    def test_create_rejects_invalid_payloads_and_other_areas(self):
        for payload in [
            [],
            {},
            {"name": " ", "secrecy_level": "SECRET"},
            {"name": "A" * 121, "secrecy_level": "SECRET"},
            {"name": "Team", "description": None, "secrecy_level": "SECRET"},
            {"name": "Team", "secrecy_level": "UNKNOWN"},
            {"name": "Team\x00", "secrecy_level": "PUBLIC"},
            {"name": "Team", "description": "Bad\x00text", "secrecy_level": "PUBLIC"},
            {"name": "Team", "secrecy_level": "PUBLIC\x00"},
            {"name": "Team", "secrecy_level": "SECRET", "area_id": self.other_area.id},
            {"name": "Team", "secrecy_level": "SECRET", "scope": "PROJECT"},
        ]:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/manager/access-groups", payload, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("errors", response.json())
        response = self.client.post("/manager/access-groups", "{", content_type="application/json")
        self.assertEqual((response.status_code, response.json()["error"]), (400, "InvalidJSON"))

    def test_create_rejects_duplicate_name_and_area_level(self):
        for payload in [
            {"name": self.group.name, "secrecy_level": "PUBLIC"},
            {"name": "Another", "secrecy_level": "SECRET"},
        ]:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/manager/access-groups", payload, content_type="application/json"
                )
                self.assertEqual(
                    (response.status_code, response.json()["error"]), (409, "AccessGroupConflict")
                )

    def test_unit_validation_rejects_invalid_name(self):
        with self.assertRaises(GroupManagementError) as caught:
            create_group(self.manager, {"name": "", "secrecy_level": "SECRET"})
        self.assertIn("name", caught.exception.errors)

    def test_members_can_be_added_listed_and_removed(self):
        member = User.objects.create_user(
            email="member@example.com",
            password="secret",
            name="Member",
            role=Role.VIEWER,
            area=self.other_area,
        )
        path = f"/manager/access-groups/{self.group.id}/users"
        response = self.client.post(path, {"user_id": member.id}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["added_by"], self.manager.id)
        self.assertEqual(
            AccessGroupMember.objects.get(group=self.group, user=member).added_by, self.manager
        )
        response = self.client.get(path)
        self.assertEqual([item["user_id"] for item in response.json()["results"]], [member.id])
        response = self.client.post(path, {"user_id": member.id}, content_type="application/json")
        self.assertEqual(
            (response.status_code, response.json()["error"]), (409, "AccessGroupMemberExists")
        )
        self.assertEqual(self.client.delete(f"{path}/{member.id}").status_code, 204)
        self.assertFalse(AccessGroupMember.objects.filter(group=self.group, user=member).exists())
        self.assertEqual(self.client.delete(f"{path}/{member.id}").status_code, 404)

    def test_member_payload_and_missing_user(self):
        path = f"/manager/access-groups/{self.group.id}/users"
        for payload in [
            {},
            {"user_id": True},
            {"user_id": -1},
            {"user_id": "1"},
            {"user_id": 1, "extra": 1},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post(path, payload, content_type="application/json").status_code,
                    400,
                )
        self.assertEqual(
            self.client.post(
                path, {"user_id": 999999}, content_type="application/json"
            ).status_code,
            404,
        )
        inactive = User.objects.create_user(
            email="inactive@example.com",
            password="secret",
            name="Inactive",
            role=Role.VIEWER,
            area=self.area,
            is_active=False,
        )
        self.assertEqual(
            self.client.post(
                path, {"user_id": inactive.id}, content_type="application/json"
            ).status_code,
            404,
        )

    def test_other_areas_and_project_groups_are_inaccessible(self):
        project = Project.objects.create(code="PROJECT", name="Project")
        project_group = AccessGroup.objects.create(
            name="Project group",
            scope=AccessGroupScope.PROJECT,
            project=project,
            secrecy_level=self.level,
            created_by=self.manager,
        )
        for group_id in [self.other_group.id, project_group.id, 999999]:
            with self.subTest(group_id=group_id):
                path = f"/manager/access-groups/{group_id}/users"
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(
                    self.client.post(
                        path, {"user_id": self.manager.id}, content_type="application/json"
                    ).status_code,
                    404,
                )
                self.assertEqual(self.client.delete(f"{path}/{self.manager.id}").status_code, 404)
        self.assertEqual(
            [item["id"] for item in self.client.get("/manager/access-groups").json()["results"]],
            [self.group.id],
        )

    def test_inactive_group_refuses_new_members(self):
        self.group.active = False
        self.group.save(update_fields=["active"])
        response = self.client.post(
            f"/manager/access-groups/{self.group.id}/users",
            {"user_id": self.manager.id},
            content_type="application/json",
        )
        self.assertEqual(
            (response.status_code, response.json()["error"]), (409, "AccessGroupInactive")
        )

    def test_authorization_applies_to_every_operation(self):
        paths = [
            ("get", "/manager/access-groups", None),
            ("post", "/manager/access-groups", {"name": "Team", "secrecy_level": "PUBLIC"}),
            ("get", f"/manager/access-groups/{self.group.id}/users", None),
            ("post", f"/manager/access-groups/{self.group.id}/users", {"user_id": self.manager.id}),
            ("delete", f"/manager/access-groups/{self.group.id}/users/{self.manager.id}", None),
        ]
        viewer = User.objects.create_user(
            email="viewer@example.com",
            password="secret",
            name="Viewer",
            role=Role.VIEWER,
            area=self.area,
        )
        for user, expected in [(None, 401), (viewer, 403)]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for method, path, payload in paths:
                with self.subTest(user=user, method=method, path=path):
                    response = getattr(self.client, method)(
                        path, data=payload, content_type="application/json"
                    )
                    self.assertEqual(response.status_code, expected)

    def test_admin_is_authorized_but_inactive_area_is_not(self):
        self.manager.role = Role.ADMIN
        self.manager.save(update_fields=["role"])
        self.assertEqual(self.client.get("/manager/access-groups").status_code, 200)
        self.area.active = False
        self.area.save(update_fields=["active"])
        self.assertEqual(self.client.get("/manager/access-groups").status_code, 403)
