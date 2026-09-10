from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from core.models import Discipline, Project


class ListProjectsViewTests(TestCase):
    def test_should_return_projects_ordered_by_name(self):
        # Given
        pilone = Project.objects.create(code="AK-3100", name="Pilone de Motor")
        fuselagem = Project.objects.create(
            code="AK-2100", name="Aeroestrutura de Fuselagem Central"
        )
        empenagem = Project.objects.create(code="AK-2200", name="Conjunto de Empenagem Vertical")

        # When
        response = self.client.get(reverse("project-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            [
                {"id": fuselagem.id, "code": "AK-2100", "name": "Aeroestrutura de Fuselagem Central"},
                {"id": empenagem.id, "code": "AK-2200", "name": "Conjunto de Empenagem Vertical"},
                {"id": pilone.id, "code": "AK-3100", "name": "Pilone de Motor"},
            ],
        )

    def test_should_return_only_active_projects(self):
        # Given
        Project.objects.create(code="AK-2100", name="Aeroestrutura de Fuselagem Central")
        Project.objects.create(code="AK-1500", name="Nacele", active=False)

        # When
        response = self.client.get(reverse("project-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["code"] for item in response.json()], ["AK-2100"])

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
        response = client.post(reverse("project-list"), {"name": "New"})

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
        materiais = Discipline.objects.create(code="MAT", name="Materiais e Processos")
        estruturas = Discipline.objects.create(code="EST", name="Estruturas")
        hidraulica = Discipline.objects.create(code="HID", name="Sistemas Hidráulicos")

        # When
        response = self.client.get(reverse("discipline-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json(),
            [
                {"id": estruturas.id, "code": "EST", "name": "Estruturas"},
                {"id": materiais.id, "code": "MAT", "name": "Materiais e Processos"},
                {"id": hidraulica.id, "code": "HID", "name": "Sistemas Hidráulicos"},
            ],
        )

    def test_should_return_only_active_disciplines(self):
        # Given
        Discipline.objects.create(code="EST", name="Estruturas")
        Discipline.objects.create(code="PNE", name="Sistemas Pneumáticos", active=False)

        # When
        response = self.client.get(reverse("discipline-list"))

        # Then
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["code"] for item in response.json()], ["EST"])

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
        response = client.post(reverse("discipline-list"), {"name": "New"})

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
