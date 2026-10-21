from django.test import SimpleTestCase

from classifier.catalog import load_catalog
from scripts.dataset.label_maps import (
    DISCIPLINE_BY_FSC_GROUP,
    DOCUMENT_TYPE_BY_CATEGORY,
    UnmappedLabelError,
    discipline_for,
    document_type_for,
)


class DocumentTypeMapTests(SimpleTestCase):
    def test_should_group_the_three_specification_categories(self):
        categories = ["Detail Specification", "Federal Specification", "Performance Specification"]

        labels = {document_type_for(category) for category in categories}

        self.assertEqual(labels, {"SPECIFICATION"})

    def test_should_map_cid_and_handbook_to_their_own_classes(self):
        self.assertEqual(document_type_for("Commercial Item Description (CID)"), "COMMERCIAL_ITEM")
        self.assertEqual(document_type_for("Defense Handbook"), "HANDBOOK")

    def test_should_group_every_military_standard_subtype_as_standard(self):
        subtypes = [
            category for category in DOCUMENT_TYPE_BY_CATEGORY if category.startswith("Military")
        ]

        labels = {document_type_for(category) for category in subtypes}

        self.assertEqual(labels, {"STANDARD"})
        self.assertEqual(len(subtypes), 6)

    def test_should_ignore_surrounding_spaces_in_the_category(self):
        self.assertEqual(document_type_for("  Defense Handbook "), "HANDBOOK")

    def test_should_fail_on_an_unknown_category_instead_of_using_a_fallback(self):
        with self.assertRaises(UnmappedLabelError):
            document_type_for("American Society for Testing and Materials (ASTM)")

    def test_should_only_produce_labels_from_the_catalog(self):
        catalog = load_catalog()

        labels = set(DOCUMENT_TYPE_BY_CATEGORY.values())

        self.assertEqual(labels, catalog["document_type"])


class DisciplineMapTests(SimpleTestCase):
    def test_should_use_only_the_first_two_digits_of_the_fsc(self):
        self.assertEqual(discipline_for("5998"), "ELECTRICAL")
        self.assertEqual(discipline_for("1680"), "MECHANICAL")
        self.assertEqual(discipline_for("9150"), "MATERIALS")

    def test_should_split_the_ten_fsc_groups_into_three_disciplines(self):
        counts = {}
        for label in DISCIPLINE_BY_FSC_GROUP.values():
            counts[label] = counts.get(label, 0) + 1

        self.assertEqual(counts, {"MECHANICAL": 4, "ELECTRICAL": 2, "MATERIALS": 4})

    def test_should_fail_on_an_unknown_fsc_group(self):
        with self.assertRaises(UnmappedLabelError):
            discipline_for("7010")

    def test_should_fail_on_an_empty_fsc(self):
        with self.assertRaises(UnmappedLabelError):
            discipline_for("")

    def test_should_only_produce_labels_from_the_catalog(self):
        catalog = load_catalog()

        labels = set(DISCIPLINE_BY_FSC_GROUP.values())

        self.assertEqual(labels, catalog["discipline"])
