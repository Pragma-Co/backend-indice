from django.test import SimpleTestCase

from core.services.partial_json_service import read_partial_string_field


class ReadPartialStringFieldTests(SimpleTestCase):
    def test_given_key_not_started_when_read_then_returns_none(self):
        text = '{"tit'

        result = read_partial_string_field(text, "title")

        self.assertIsNone(result)

    def test_given_unfinished_value_when_read_then_returns_text_so_far(self):
        text = '{"title": "Memorial de Cál'

        result = read_partial_string_field(text, "title")

        self.assertEqual(result, ("Memorial de Cál", False))

    def test_given_finished_value_when_read_then_marks_it_finished(self):
        text = '{"title": "Memorial", "subtitle": "Dimens'

        result = read_partial_string_field(text, "title")

        self.assertEqual(result, ("Memorial", True))

    def test_given_second_key_when_read_then_returns_its_own_value(self):
        text = '{"title": "Memorial", "subtitle": "Dimens'

        result = read_partial_string_field(text, "subtitle")

        self.assertEqual(result, ("Dimens", False))

    def test_given_escaped_quote_when_read_then_keeps_reading_the_value(self):
        text = '{"title": "Viga \\"principal\\" da asa'

        result = read_partial_string_field(text, "title")

        self.assertEqual(result, ('Viga "principal" da asa', False))

    def test_given_key_quoted_inside_a_value_when_read_then_ignores_it(self):
        text = '{"title": "Campo \\"subtitle\\": \\"x\\" explicado'

        result = read_partial_string_field(text, "subtitle")

        self.assertIsNone(result)

    def test_given_trailing_backslash_when_read_then_leaves_it_out(self):
        text = '{"title": "Linha um\\'

        result = read_partial_string_field(text, "title")

        self.assertEqual(result, ("Linha um", False))

    def test_given_unfinished_unicode_escape_when_read_then_leaves_it_out(self):
        text = '{"title": "C\\u00e1lculo de press\\u00e'

        result = read_partial_string_field(text, "title")

        self.assertEqual(result, ("Cálculo de press", False))

    def test_given_half_surrogate_pair_when_read_then_leaves_it_out(self):
        text = '{"title": "Asa \\ud83d'

        result = read_partial_string_field(text, "title")

        self.assertEqual(result, ("Asa ", False))

    def test_given_raw_line_break_when_read_then_keeps_the_value(self):
        text = '{"title": "Linha um\nLinha dois"'

        result = read_partial_string_field(text, "title")

        self.assertEqual(result, ("Linha um\nLinha dois", True))
