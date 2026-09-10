from django.test import TestCase

from core.models import Discipline, Project
from core.services.catalog_service import list_active_disciplines, list_active_projects


class ListActiveProjectsTests(TestCase):
    def test_should_return_only_active_projects_ordered_by_name(self):
        # Given
        Project.objects.create(code="AK-3100", name="Pilone de Motor")
        Project.objects.create(code="AK-2100", name="Aeroestrutura de Fuselagem Central")
        Project.objects.create(code="AK-1500", name="Nacele", active=False)

        # When
        codes = [project.code for project in list_active_projects()]

        # Then
        self.assertEqual(codes, ["AK-2100", "AK-3100"])

    def test_should_return_empty_queryset_without_projects(self):
        # Given: no projects

        # When
        projects = list(list_active_projects())

        # Then
        self.assertEqual(projects, [])


class ListActiveDisciplinesTests(TestCase):
    def test_should_return_only_active_disciplines_ordered_by_name(self):
        # Given
        Discipline.objects.create(code="MAT", name="Materiais e Processos")
        Discipline.objects.create(code="EST", name="Estruturas")
        Discipline.objects.create(code="PNE", name="Sistemas Pneumáticos", active=False)

        # When
        codes = [discipline.code for discipline in list_active_disciplines()]

        # Then
        self.assertEqual(codes, ["EST", "MAT"])

    def test_should_return_empty_queryset_without_disciplines(self):
        # Given: no disciplines

        # When
        disciplines = list(list_active_disciplines())

        # Then
        self.assertEqual(disciplines, [])
