from django.test import SimpleTestCase

from scripts.dataset.details import sample_rows


def listing_row(ident_number: int, document_id: str, fsc: str = "5310") -> dict:
    return {"ident_number": ident_number, "document_id": document_id, "fsc": fsc}


class SampleRowsTests(SimpleTestCase):
    def rows(self) -> list[dict]:
        specs = [listing_row(number, f"MIL-DTL-{number}") for number in range(1, 11)]
        standards = [listing_row(100 + number, f"MIL-STD-{number}") for number in range(1, 4)]
        handbooks = [listing_row(200 + number, f"MIL-HDBK-{number}") for number in range(1, 3)]
        return specs + standards + handbooks

    def test_should_limit_each_fsc_group_to_the_requested_size_by_default(self):
        sampled = sample_rows(self.rows(), per_group=2)

        self.assertEqual(len(sampled), 2)

    def test_should_add_every_standard_and_handbook_when_asked(self):
        sampled = sample_rows(self.rows(), per_group=2, include_standards_and_handbooks=True)

        ids = {row["document_id"] for row in sampled}
        self.assertTrue({"MIL-STD-1", "MIL-STD-3", "MIL-HDBK-1", "MIL-HDBK-2"} <= ids)

    def test_should_not_repeat_a_document_that_was_already_sampled(self):
        sampled = sample_rows(self.rows(), per_group=20, include_standards_and_handbooks=True)

        numbers = [row["ident_number"] for row in sampled]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_should_keep_the_default_sample_identical_when_the_option_is_off(self):
        first = sample_rows(self.rows(), per_group=4)

        second = sample_rows(self.rows(), per_group=4, include_standards_and_handbooks=False)

        self.assertEqual(first, second)

    def test_should_skip_groups_outside_the_selected_fsc_list(self):
        rows = [listing_row(1, "MIL-STD-1", fsc="1560"), listing_row(2, "MIL-STD-2", fsc="59GP")]

        sampled = sample_rows(rows, per_group=5, include_standards_and_handbooks=True)

        self.assertEqual(sampled, [])
