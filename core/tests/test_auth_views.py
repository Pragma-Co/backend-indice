from django.contrib.sessions.models import Session
from django.test import Client, TestCase

from core.models import Area, User

CSRF_TOKEN = "f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6"


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
