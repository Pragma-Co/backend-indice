from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from core.models import Discipline, Project


class ListProjectsViewTests(TestCase):
    def test_should_return_projects_ordered_by_name(self):
        # Given
        gama = Project.objects.create(code="PJT003", name="Projeto Gama")
        alfa = Project.objects.create(code="PJT001", name="Projeto Alfa")
        beta = Project.objects.create(code="PJT002", name="Projeto Beta")

        # When
        response = self.client.get(reverse("project-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            [
                {"id": alfa.id, "code": "PJT001", "name": "Projeto Alfa"},
                {"id": beta.id, "code": "PJT002", "name": "Projeto Beta"},
                {"id": gama.id, "code": "PJT003", "name": "Projeto Gama"},
            ],
        )

    def test_should_return_only_active_projects(self):
        # Given
        Project.objects.create(code="PJT001", name="Projeto Alfa")
        Project.objects.create(code="PJT099", name="Projeto Encerrado", active=False)

        # When
        response = self.client.get(reverse("project-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["code"] for item in response.json()], ["PJT001"])

    def test_should_return_empty_list_without_projects(self):
        # Given: no projects

        # When
        response = self.client.get(reverse("project-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_should_answer_405_for_disallowed_methods(self):
        # Given
        url = reverse("project-list")

        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                # When
                response = getattr(self.client, method)(url)

                # Then
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")

    def test_should_answer_405_even_with_csrf_checks_enforced(self):
        # Given: a browser-like client that does not skip the CSRF middleware
        client = Client(enforce_csrf_checks=True)

        # When
        response = client.post(reverse("project-list"), {"name": "Novo"})

        # Then
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "GET")

    def test_should_hide_internal_details_on_error(self):
        # Given
        internal_detail = 'connection to server at "postgres" (10.0.0.5) failed'
        with patch(
            "core.views.catalog_view.list_active_projects",
            side_effect=RuntimeError(internal_detail),
        ), self.assertLogs("core.views.catalog_view", level="ERROR") as logs:
            # When
            response = self.client.get(reverse("project-list"))

        # Then
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})
        self.assertNotIn("postgres", response.content.decode())
        self.assertIn(internal_detail, "\n".join(logs.output))


class ListDisciplinesViewTests(TestCase):
    def test_should_return_disciplines_ordered_by_name(self):
        # Given
        tubulacao = Discipline.objects.create(name="Tubulação")
        eletrica = Discipline.objects.create(name="Elétrica")
        manufatura = Discipline.objects.create(name="Manufatura")

        # When
        response = self.client.get(reverse("discipline-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            [
                {"id": eletrica.id, "acronym": "ELE", "name": "Elétrica"},
                {"id": manufatura.id, "acronym": "MAN", "name": "Manufatura"},
                {"id": tubulacao.id, "acronym": "TUB", "name": "Tubulação"},
            ],
        )

    def test_should_return_only_active_disciplines(self):
        # Given
        Discipline.objects.create(name="Tubulação")
        Discipline.objects.create(name="Descontinuada", active=False)

        # When
        response = self.client.get(reverse("discipline-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["acronym"] for item in response.json()], ["TUB"])

    def test_should_return_empty_list_without_disciplines(self):
        # Given: no disciplines

        # When
        response = self.client.get(reverse("discipline-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_should_answer_405_for_disallowed_methods(self):
        # Given
        url = reverse("discipline-list")

        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                # When
                response = getattr(self.client, method)(url)

                # Then
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")

    def test_should_answer_405_even_with_csrf_checks_enforced(self):
        # Given: a browser-like client that does not skip the CSRF middleware
        client = Client(enforce_csrf_checks=True)

        # When
        response = client.post(reverse("discipline-list"), {"name": "Nova"})

        # Then
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "GET")

    def test_should_hide_internal_details_on_error(self):
        # Given
        internal_detail = "FATAL: password authentication failed for user api6_admin"
        with patch(
            "core.views.catalog_view.list_active_disciplines",
            side_effect=RuntimeError(internal_detail),
        ), self.assertLogs("core.views.catalog_view", level="ERROR") as logs:
            # When
            response = self.client.get(reverse("discipline-list"))

        # Then
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "RuntimeError"})
        self.assertNotIn("api6_admin", response.content.decode())
        self.assertIn(internal_detail, "\n".join(logs.output))


class ApiRootViewTests(TestCase):
    def test_should_list_catalog_routes(self):
        # Given
        url = reverse("api-root")

        # When
        response = self.client.get(url)

        # Then
        self.assertEqual(response.status_code, 200)
        endpoints = response.json()["endpoints"]
        self.assertEqual(endpoints["projects"], "/projects/")
        self.assertEqual(endpoints["disciplines"], "/disciplines/")
