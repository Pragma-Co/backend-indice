from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Discipline, Project

EXPECTED_ACRONYMS = {
    "Engenharia": "ENG",
    "Manufatura": "MAN",
    "Qualidade": "QUA",
    "Configuração": "CON",
    "Tubulação": "TUB",
    "Estrutura": "EST",
    "Elétrica": "ELE",
}


def run_seed() -> str:
    output = StringIO()
    call_command("seed_catalogs", stdout=output)
    return output.getvalue()


class SeedCatalogsCommandTests(TestCase):
    def test_should_create_default_projects_and_disciplines(self):
        # Given: empty catalogs
        self.assertEqual(Project.objects.count(), 0)
        self.assertEqual(Discipline.objects.count(), 0)

        # When
        output = run_seed()

        # Then
        self.assertEqual(
            list(Project.objects.values_list("code", "name")),
            [
                ("PJT001", "Projeto Alfa"),
                ("PJT002", "Projeto Beta"),
                ("PJT003", "Projeto Gama"),
            ],
        )
        self.assertEqual(dict(Discipline.objects.values_list("name", "acronym")), EXPECTED_ACRONYMS)
        self.assertFalse(Project.objects.filter(active=False).exists())
        self.assertFalse(Discipline.objects.filter(active=False).exists())
        self.assertIn("3 project(s) and 7 discipline(s) created", output)

    def test_should_be_idempotent(self):
        # Given
        run_seed()
        project_ids = set(Project.objects.values_list("id", flat=True))
        discipline_ids = set(Discipline.objects.values_list("id", flat=True))

        # When
        output = run_seed()

        # Then
        self.assertEqual(Project.objects.count(), 3)
        self.assertEqual(Discipline.objects.count(), 7)
        self.assertEqual(set(Project.objects.values_list("id", flat=True)), project_ids)
        self.assertEqual(set(Discipline.objects.values_list("id", flat=True)), discipline_ids)
        self.assertIn("0 project(s) and 0 discipline(s) created", output)

    def test_should_not_overwrite_changes_made_after_seeding(self):
        # Given
        run_seed()
        Project.objects.filter(code="PJT001").update(name="Projeto Alfa Renomeado", active=False)

        # When
        run_seed()

        # Then
        project = Project.objects.get(code="PJT001")
        self.assertEqual(project.name, "Projeto Alfa Renomeado")
        self.assertFalse(project.active)

    def test_should_only_add_missing_entries(self):
        # Given
        Project.objects.create(code="PJT002", name="Projeto Beta")
        Discipline.objects.create(name="Tubulação")

        # When
        output = run_seed()

        # Then
        self.assertEqual(Project.objects.count(), 3)
        self.assertEqual(Discipline.objects.count(), 7)
        self.assertIn("2 project(s) and 6 discipline(s) created", output)
