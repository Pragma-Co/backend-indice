from django.test import SimpleTestCase

from core.services.acronym_service import generate_acronym, is_valid_acronym, strip_accents


class GenerateAcronymTests(SimpleTestCase):
    def test_should_use_the_first_three_letters_upper_cased(self):
        # Given
        name = "Tubulação"

        # When
        acronym = generate_acronym(name)

        # Then
        self.assertEqual(acronym, "TUB")

    def test_should_ignore_accents_and_spaces(self):
        # Given
        names = {
            "Memória de Cálculo": "MEM",
            "Elétrica": "ELE",
            "Revisão Técnica": "REV",
            "  Ção Teste": "CAO",
        }

        for name, expected in names.items():
            with self.subTest(name=name):
                # When
                acronym = generate_acronym(name)

                # Then
                self.assertEqual(acronym, expected)

    def test_should_ignore_digits_and_punctuation(self):
        # Given
        name = "3D - Modelagem"

        # When
        acronym = generate_acronym(name)

        # Then
        self.assertEqual(acronym, "DMO")

    def test_should_return_incomplete_acronym_for_short_name(self):
        # Given
        name = "Ar"

        # When
        acronym = generate_acronym(name)

        # Then
        self.assertEqual(acronym, "AR")
        self.assertFalse(is_valid_acronym(acronym))


class IsValidAcronymTests(SimpleTestCase):
    def test_should_accept_three_upper_case_letters(self):
        # Given
        acronym = "TUB"

        # When
        valid = is_valid_acronym(acronym)

        # Then
        self.assertTrue(valid)

    def test_should_reject_invalid_formats(self):
        # Given
        invalid = ["tub", "TU", "TUBO", "TU1", "TÚB", "", None]

        for acronym in invalid:
            with self.subTest(acronym=acronym):
                # When
                valid = is_valid_acronym(acronym)

                # Then
                self.assertFalse(valid)


class StripAccentsTests(SimpleTestCase):
    def test_should_remove_every_accent(self):
        # Given
        text = "Configuração Elétrica"

        # When
        result = strip_accents(text)

        # Then
        self.assertEqual(result, "Configuracao Eletrica")
