import json

from django.test import Client, TestCase, override_settings

from core.models import Area, Role, User


@override_settings(DEBUG=True)
class DevLoginViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.area = Area.objects.create(acronym="QUA", name="Qualidade e Inspeção")
        self.auditor = User.objects.create_user(
            email="auditor@example.com",
            password="secret",
            name="Auditor",
            area=self.area,
            role=Role.AUDITOR,
        )

    def _post(self, payload):
        return self.client.post(
            "/dev/login", data=json.dumps(payload), content_type="application/json"
        )

    def test_opens_a_session_for_the_given_user(self):
        response = self._post({"user_id": self.auditor.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.auditor.pk)
        self.assertEqual(response.json()["role"], Role.AUDITOR)
        self.assertEqual(self.client.get("/users/me").json()["id"], self.auditor.pk)

    def test_session_gives_access_to_the_manager_endpoints(self):
        before = self.client.get("/manager/pending-revisions")

        self._post({"user_id": self.auditor.pk})
        after = self.client.get("/manager/pending-revisions")

        self.assertEqual(before.status_code, 401)
        self.assertEqual(after.status_code, 200)

    def test_signing_in_again_switches_the_session_user(self):
        author = User.objects.create_user(
            email="author@example.com",
            password="secret",
            name="Author",
            area=self.area,
            role=Role.AUTHOR,
        )
        self._post({"user_id": self.auditor.pk})

        self._post({"user_id": author.pk})

        self.assertEqual(self.client.get("/users/me").json()["id"], author.pk)
        self.assertEqual(self.client.get("/manager/pending-revisions").status_code, 403)

    def test_rejects_a_missing_or_invalid_user_id(self):
        for payload in ({}, {"user_id": "10"}, {"user_id": True}, [1]):
            with self.subTest(payload=payload):
                response = self._post(payload)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"error": "MissingUser"})

    def test_rejects_a_body_that_is_not_json(self):
        response = self.client.post("/dev/login", data="not json", content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "InvalidJSON"})

    def test_does_not_sign_in_an_unknown_or_inactive_user(self):
        inactive = User.objects.create_user(
            email="inactive@example.com",
            password="secret",
            name="Inactive",
            area=self.area,
            is_active=False,
        )

        for user_id in (999999, inactive.pk):
            with self.subTest(user_id=user_id):
                response = self._post({"user_id": user_id})

                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"error": "UserNotFound"})
        self.assertEqual(self.client.get("/users/me").status_code, 401)

    def test_only_accepts_post(self):
        self.assertEqual(self.client.get("/dev/login").status_code, 405)

    @override_settings(DEBUG=False)
    def test_is_not_available_outside_debug(self):
        response = self._post({"user_id": self.auditor.pk})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/users/me").status_code, 401)
