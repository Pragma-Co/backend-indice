from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import Project


class ProjectModelTests(TestCase):
    def test_should_create_project_active_by_default(self):
        # Given / When
        project = Project.objects.create(code="PJT001", name="Projeto Alfa")

        # Then
        self.assertTrue(project.active)
        self.assertIsNotNone(project.created_at)

    def test_should_not_allow_duplicate_code(self):
        # Given
        Project.objects.create(code="PJT001", name="Projeto Alfa")

        # When / Then
        with self.assertRaises(IntegrityError), transaction.atomic():
            Project.objects.create(code="PJT001", name="Outro Projeto")

    def test_should_reject_code_longer_than_twenty_characters(self):
        # Given
        project = Project(code="P" * 21, name="Projeto Longo")

        # When / Then
        with self.assertRaises(ValidationError) as context:
            project.full_clean()
        self.assertIn("code", context.exception.message_dict)

    def test_should_reject_empty_code(self):
        # Given
        project = Project(code="", name="Sem Código")

        # When / Then
        with self.assertRaises(ValidationError) as context:
            project.full_clean()
        self.assertIn("code", context.exception.message_dict)

    def test_should_order_projects_by_name(self):
        # Given
        Project.objects.create(code="PJT003", name="Projeto Gama")
        Project.objects.create(code="PJT001", name="Projeto Alfa")
        Project.objects.create(code="PJT002", name="Projeto Beta")

        # When
        codes = list(Project.objects.values_list("code", flat=True))

        # Then
        self.assertEqual(codes, ["PJT001", "PJT002", "PJT003"])

    def test_should_represent_as_code_and_name(self):
        # Given
        project = Project(code="PJT001", name="Projeto Alfa")

        # When
        text = str(project)

        # Then
        self.assertEqual(text, "PJT001 - Projeto Alfa")
