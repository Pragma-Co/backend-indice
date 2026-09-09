from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import Discipline


class DisciplineModelTests(TestCase):
    def test_should_generate_acronym_automatically_on_save(self):
        # Given
        discipline = Discipline(name="Tubulação")

        # When
        discipline.save()

        # Then
        discipline.refresh_from_db()
        self.assertEqual(discipline.acronym, "TUB")

    def test_should_generate_acronym_without_accents_ignoring_spaces(self):
        # Given
        discipline = Discipline(name="Memória de Cálculo")

        # When
        discipline.save()

        # Then
        self.assertEqual(discipline.acronym, "MEM")

    def test_should_keep_explicitly_given_acronym(self):
        # Given
        discipline = Discipline(name="Engenharia", acronym="ENA")

        # When
        discipline.save()

        # Then
        self.assertEqual(discipline.acronym, "ENA")

    def test_should_fill_acronym_on_full_clean(self):
        # Given
        discipline = Discipline(name="Qualidade")

        # When
        discipline.full_clean()

        # Then
        self.assertEqual(discipline.acronym, "QUA")

    def test_should_reject_malformed_acronym_on_full_clean(self):
        # Given
        invalid_acronyms = ["tub", "TU", "TUBO", "TU1"]

        for acronym in invalid_acronyms:
            with self.subTest(acronym=acronym):
                discipline = Discipline(name="Tubulação", acronym=acronym)

                # When / Then
                with self.assertRaises(ValidationError) as context:
                    discipline.full_clean()
                self.assertIn("acronym", context.exception.message_dict)

    def test_should_reject_malformed_acronym_on_save(self):
        # Given
        discipline = Discipline(name="Tubulação", acronym="tub")

        # When / Then
        with self.assertRaises(ValidationError):
            discipline.save()
        self.assertEqual(Discipline.objects.count(), 0)

    def test_should_reject_name_too_short_to_build_acronym(self):
        # Given
        discipline = Discipline(name="Ar")

        # When / Then
        with self.assertRaises(ValidationError):
            discipline.save()

    def test_should_not_allow_duplicate_acronym(self):
        # Given
        Discipline.objects.create(name="Tubulação")

        # When / Then
        with self.assertRaises(IntegrityError), transaction.atomic():
            Discipline.objects.create(name="Tubos")

    def test_should_be_active_by_default(self):
        # Given / When
        discipline = Discipline.objects.create(name="Estrutura")

        # Then
        self.assertTrue(discipline.active)
        self.assertIsNotNone(discipline.created_at)

    def test_should_order_disciplines_by_name(self):
        # Given
        Discipline.objects.create(name="Tubulação")
        Discipline.objects.create(name="Elétrica")
        Discipline.objects.create(name="Manufatura")

        # When
        names = list(Discipline.objects.values_list("name", flat=True))

        # Then
        self.assertEqual(names, ["Elétrica", "Manufatura", "Tubulação"])

    def test_should_represent_as_acronym_and_name(self):
        # Given
        discipline = Discipline.objects.create(name="Tubulação")

        # When
        text = str(discipline)

        # Then
        self.assertEqual(text, "TUB - Tubulação")
