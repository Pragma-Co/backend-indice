from collections import Counter

from django.test import SimpleTestCase

from scripts.dataset.build_csv import MIN_TEXT_CHARS, build_rows
from scripts.dataset.document_group import group_key

LONG_TEXT = "requirement " * (MIN_TEXT_CHARS // 8)


def record(ident_number: int, **overrides) -> dict:
    values = {
        "ident_number": ident_number,
        "document_id": f"MIL-DTL-{ident_number}",
        "doc_category": "Detail Specification",
        "fsc": "5998",
        "selected_part": {"token": "t"},
    }
    return {**values, **overrides}


def build(records, text=LONG_TEXT):
    skipped = Counter()
    rows = build_rows(records, lambda item: text, skipped)
    return rows, skipped


class BuildRowsTests(SimpleTestCase):
    def test_should_label_type_and_discipline_by_rule_and_leave_area_for_the_labeler(self):
        rows, _ = build([record(1)])

        self.assertEqual(rows[0]["document_type"], "SPECIFICATION")
        self.assertEqual(rows[0]["discipline"], "ELECTRICAL")
        self.assertEqual(rows[0]["area"], "")

    def test_should_carry_the_title_so_the_labeler_can_read_it(self):
        rows, _ = build([record(1, title="Cable, Radio Frequency")])

        self.assertEqual(rows[0]["title"], "Cable, Radio Frequency")

    def test_should_skip_documents_without_a_public_part(self):
        rows, skipped = build([record(1, selected_part=None)])

        self.assertEqual(rows, [])
        self.assertEqual(skipped["no public part"], 1)

    def test_should_skip_and_count_a_category_that_has_no_mapping(self):
        category = "American Society for Testing and Materials (ASTM)"

        rows, skipped = build([record(1, doc_category=category)])

        self.assertEqual(rows, [])
        self.assertEqual(sum(skipped.values()), 1)
        self.assertTrue(any("unmapped" in reason for reason in skipped))

    def test_should_skip_documents_with_too_little_text(self):
        rows, skipped = build([record(1)], text="short")

        self.assertEqual(rows, [])
        self.assertEqual(skipped["too little text"], 1)

    def test_should_skip_documents_whose_pdf_cannot_be_read(self):
        skipped = Counter()

        rows = build_rows([record(1)], lambda item: None, skipped)

        self.assertEqual(rows, [])
        self.assertEqual(skipped["pdf not downloaded or unreadable"], 1)

    def test_should_keep_a_single_row_per_document(self):
        duplicated = [record(2, document_id="MIL-DTL-1"), record(1, document_id="MIL-DTL-1")]

        rows, skipped = build(duplicated)

        self.assertEqual([row["ident_number"] for row in rows], [1])
        self.assertEqual(skipped["duplicate document"], 1)

    def test_should_produce_the_same_rows_for_the_same_records_in_any_order(self):
        records = [record(3), record(1), record(2)]

        first, _ = build(records)
        second, _ = build(list(reversed(records)))

        self.assertEqual(first, second)


class GroupKeyTests(SimpleTestCase):
    def test_should_strip_the_revision_letter(self):
        self.assertEqual(group_key("MIL-STD-810H"), "MIL-STD-810")
        self.assertEqual(group_key("MIL-DTL-83513/1B"), "MIL-DTL-83513/1")

    def test_should_strip_notices_amendments_and_supplements(self):
        self.assertEqual(group_key("MIL-PRF-1/36J NOT 2"), "MIL-PRF-1/36")
        self.assertEqual(group_key("MIL-PRF-1N(1) SUP 1 NOT 1"), "MIL-PRF-1")

    def test_should_keep_documents_without_revision_untouched(self):
        self.assertEqual(group_key("A-A-59812"), "A-A-59812")

    def test_should_give_every_revision_of_a_document_the_same_group(self):
        keys = {group_key(value) for value in ("MIL-HDBK-5H", "MIL-HDBK-5J", "MIL-HDBK-5J NOT 1")}

        self.assertEqual(keys, {"MIL-HDBK-5"})
