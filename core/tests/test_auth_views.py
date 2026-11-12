import json

from django.contrib.sessions.models import Session
from django.test import Client, TestCase

from core.models import Area, User

CSRF_TOKEN = "f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6"
PASSWORD = "Correct-Horse-42"


class LogoutViewTests(TestCase):
    def setUp(self):
        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="titular@example.com", password="secret", name="Titular", area=area
        )

    def test_should_end_the_session_and_expire_its_cookie(self):
        client = Client()
        client.force_login(self.user)
        session_key = client.session.session_key

        response = client.post("/auth/logout")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies["sessionid"].value, "")
        self.assertEqual(response.cookies["sessionid"]["max-age"], 0)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        self.assertEqual(client.get("/users/me").status_code, 401)

    def test_should_answer_204_without_a_session(self):
        response = Client().post("/auth/logout")

        self.assertEqual(response.status_code, 204)

    def test_should_require_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post("/auth/logout", HTTP_ORIGIN="http://localhost:5173")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.get("/users/me").status_code, 200)

    def test_should_log_out_from_the_frontend_origin_with_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.cookies["csrftoken"] = CSRF_TOKEN

        response = client.post(
            "/auth/logout", HTTP_X_CSRFTOKEN=CSRF_TOKEN, HTTP_ORIGIN="http://localhost:5173"
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(client.get("/users/me").status_code, 401)

    def test_should_only_accept_post(self):
        self.assertEqual(Client().get("/auth/logout").status_code, 405)


class CsrfViewTests(TestCase):
    def test_should_set_the_csrf_cookie_without_a_body(self):
        client = Client(enforce_csrf_checks=True)

        response = client.get("/auth/csrf")

        self.assertEqual(response.status_code, 204)
        self.assertIn("csrftoken", response.cookies)
        self.assertTrue(response.cookies["csrftoken"].value)

    def test_should_only_accept_get(self):
        response = Client().post("/auth/csrf")

        self.assertEqual(response.status_code, 405)


class LoginViewTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="titular@example.com", password=PASSWORD, name="Titular", area=self.area
        )

    def _post(self, payload, client=None, **extra):
        return (client or self.client).post(
            "/auth/login", data=json.dumps(payload), content_type="application/json", **extra
        )

    def test_should_open_the_session_and_return_the_user(self):
        payload = {"email": "titular@example.com", "password": PASSWORD}

        response = self._post(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.pk)
        self.assertEqual(response.json()["email"], "titular@example.com")
        self.assertEqual(response.json()["area"]["acronym"], "EST")
        self.assertNotIn("password", response.json())
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_should_answer_the_same_body_for_a_wrong_password_and_an_unknown_email(self):
        wrong_password = {"email": "titular@example.com", "password": "wrong-password"}
        unknown_email = {"email": "nobody@example.com", "password": PASSWORD}

        responses = [self._post(wrong_password), self._post(unknown_email)]

        for response in responses:
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"error": "InvalidCredentials"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_should_refuse_an_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self._post({"email": "titular@example.com", "password": PASSWORD})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "InvalidCredentials"})

    def test_should_report_missing_fields(self):
        cases = [
            {},
            {"email": "", "password": ""},
            {"email": "   ", "password": None},
            {"email": 10, "password": 10},
        ]

        responses = [self._post(payload) for payload in cases]

        for payload, response in zip(cases, responses, strict=True):
            with self.subTest(payload=payload):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {
                        "errors": {
                            "email": "Email is required.",
                            "password": "Password is required.",
                        }
                    },
                )

    def test_should_report_an_invalid_email_format(self):
        payload = {"email": "not-an-email", "password": PASSWORD}

        response = self._post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"errors": {"email": "Enter a valid email address."}})

    def test_should_reject_a_body_that_is_not_a_json_object(self):
        bodies = ["not json", "[1, 2]", ""]

        responses = [
            self.client.post("/auth/login", data=body, content_type="application/json")
            for body in bodies
        ]

        for body, response in zip(bodies, responses, strict=True):
            with self.subTest(body=body):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"error": "InvalidJSON"})

    def test_should_only_accept_post(self):
        response = self.client.get("/auth/login")

        self.assertEqual(response.status_code, 405)

    def test_should_require_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)

        response = self._post(
            {"email": "titular@example.com", "password": PASSWORD},
            client=client,
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.get("/users/me").status_code, 401)

    def test_should_sign_in_from_the_frontend_origin_with_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.cookies["csrftoken"] = CSRF_TOKEN

        response = self._post(
            {"email": "titular@example.com", "password": PASSWORD},
            client=client,
            HTTP_X_CSRFTOKEN=CSRF_TOKEN,
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        self.assertNotEqual(response.cookies["csrftoken"].value, CSRF_TOKEN)

    def test_should_sign_in_after_fetching_the_csrf_cookie(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get("/auth/csrf").cookies["csrftoken"].value

        response = self._post(
            {"email": "titular@example.com", "password": PASSWORD},
            client=client,
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response.status_code, 200)

    def test_should_keep_the_session_until_logout(self):
        self._post({"email": "titular@example.com", "password": PASSWORD})

        profile = self.client.get("/users/me")
        logout = self.client.post("/auth/logout")
        after_logout = self.client.get("/users/me")

        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["id"], self.user.pk)
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(after_logout.status_code, 401)
        self.assertEqual(after_logout.json(), {"error": "AuthenticationRequired"})
