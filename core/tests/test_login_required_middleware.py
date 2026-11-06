from django.test import TestCase
from django.urls import reverse

from core.models import Area, User

PROTECTED_ROUTES = [
    ("document-list", {}),
    ("document-search", {}),
    ("document-file-view", {"file_id": 1}),
    ("project-list", {}),
    ("manager-activities", {}),
]
PUBLIC_ROUTES = ["api-root", "health-check", "legal-document-list", "auth-csrf"]


class LoginRequiredJsonMiddlewareTests(TestCase):
    def setUp(self):
        area = Area.objects.create(acronym="EST", name="Engenharia Estrutural")
        self.user = User.objects.create_user(
            email="titular@example.com", password="Correct-Horse-42", name="Titular", area=area
        )

    def test_should_refuse_anonymous_requests_to_protected_routes(self):
        urls = [reverse(name, kwargs=kwargs) for name, kwargs in PROTECTED_ROUTES]

        responses = [self.client.get(url) for url in urls]

        for url, response in zip(urls, responses, strict=True):
            with self.subTest(url=url):
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {"error": "AuthenticationRequired"})

    def test_should_refuse_anonymous_writes_before_the_view(self):
        url = reverse("document-upload")

        response = self.client.post(url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})

    def test_should_let_anonymous_requests_reach_public_routes(self):
        urls = [reverse(name) for name in PUBLIC_ROUTES]

        responses = [self.client.get(url) for url in urls]

        for url, response in zip(urls, responses, strict=True):
            with self.subTest(url=url):
                self.assertNotEqual(response.status_code, 401)

    def test_should_let_the_admin_handle_its_own_login(self):
        url = reverse("admin:index")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_should_let_an_authenticated_user_through(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("project-list"))

        self.assertEqual(response.status_code, 200)

    def test_should_refuse_the_session_of_a_deactivated_user(self):
        self.client.force_login(self.user)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.get(reverse("project-list"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "AuthenticationRequired"})

    def test_should_answer_404_for_an_unknown_path(self):
        url = "/does-not-exist"

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_should_let_preflight_requests_through(self):
        url = reverse("document-list")

        response = self.client.options(url, HTTP_ORIGIN="http://localhost:5173")

        self.assertNotEqual(response.status_code, 401)
