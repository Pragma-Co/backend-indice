import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.catalog import (
    DEFAULT_CATALOG_PATH,
    DOCUMENT_TYPES,
    CatalogError,
    load_area_groups,
    load_area_stages,
    load_catalog,
    load_criteria_version,
)


def valid_catalog() -> dict:
    return {
        "criteria_version": "1",
        "discipline": ["MECHANICAL", "ELECTRICAL", "MATERIALS"],
        "document_type": sorted(DOCUMENT_TYPES),
        "area": ["DESIGN", "OTHER_STAGE"],
        "area_stages": ["DESIGN", "PROCESSING"],
        "area_groups": {"DESIGN": "DESIGN", "PROCESSING": "OTHER_STAGE"},
    }


class CatalogTests(SimpleTestCase):
    def write_catalog(self, **overrides) -> Path:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = directory / "catalog.json"
        path.write_text(json.dumps({**valid_catalog(), **overrides}), encoding="utf-8")
        return path

    def test_should_load_the_shipped_catalog_with_the_four_document_types(self):
        catalog = load_catalog(DEFAULT_CATALOG_PATH)

        self.assertEqual(catalog["document_type"], DOCUMENT_TYPES)
        self.assertEqual(len(catalog["discipline"]), 3)

    def test_should_expose_the_criteria_version_of_the_shipped_catalog(self):
        version = load_criteria_version(DEFAULT_CATALOG_PATH)

        self.assertEqual(version, "2")

    def test_should_reject_an_empty_label_list(self):
        path = self.write_catalog(area=[])

        with self.assertRaisesMessage(CatalogError, "area: expected a non-empty list"):
            load_catalog(path)

    def test_should_reject_duplicated_labels(self):
        path = self.write_catalog(discipline=["MECHANICAL", "MECHANICAL"])

        with self.assertRaisesMessage(CatalogError, "discipline: duplicated labels"):
            load_catalog(path)

    def test_should_reject_document_types_other_than_the_four_classes(self):
        path = self.write_catalog(document_type=["STANDARD", "HANDBOOK", "SPECIFICATION"])

        with self.assertRaisesMessage(CatalogError, "document_type: expected exactly"):
            load_catalog(path)

    def test_should_group_the_six_labeler_stages_into_three_area_classes(self):
        catalog = load_catalog(DEFAULT_CATALOG_PATH)

        stages = load_area_stages(DEFAULT_CATALOG_PATH)
        groups = load_area_groups(DEFAULT_CATALOG_PATH)

        self.assertEqual(len(stages), 6)
        self.assertEqual(catalog["area"], {"DESIGN", "MATERIALS", "OTHER_STAGE"})
        self.assertEqual(groups["DESIGN"], "DESIGN")
        self.assertEqual(groups["MATERIALS"], "MATERIALS")
        rare = {"PROCESSING", "INSPECTION_TEST", "PACKAGING_STORAGE", "NO_CLEAR_STAGE"}
        self.assertEqual({groups[stage] for stage in rare}, {"OTHER_STAGE"})

    def test_should_load_a_valid_area_grouping(self):
        path = self.write_catalog()

        self.assertEqual(load_area_stages(path), {"DESIGN", "PROCESSING"})
        self.assertEqual(load_area_groups(path)["PROCESSING"], "OTHER_STAGE")

    def test_should_reject_a_stage_that_has_no_group(self):
        path = self.write_catalog(area_groups={"DESIGN": "DESIGN"})

        with self.assertRaisesMessage(CatalogError, "area_groups: expected one entry"):
            load_area_groups(path)

    def test_should_reject_a_group_that_is_not_an_area_class(self):
        path = self.write_catalog(area_groups={"DESIGN": "DESIGN", "PROCESSING": "SOMETHING"})

        with self.assertRaisesMessage(CatalogError, "exactly the area classes"):
            load_area_groups(path)

    def test_should_reject_an_area_class_that_no_stage_maps_to(self):
        path = self.write_catalog(area_groups={"DESIGN": "DESIGN", "PROCESSING": "DESIGN"})

        with self.assertRaisesMessage(CatalogError, "exactly the area classes"):
            load_area_groups(path)

    def test_should_reject_duplicated_stages(self):
        path = self.write_catalog(area_stages=["DESIGN", "DESIGN"])

        with self.assertRaisesMessage(CatalogError, "area_stages"):
            load_area_stages(path)

    def test_should_reject_a_missing_criteria_version(self):
        path = self.write_catalog(criteria_version=" ")

        with self.assertRaisesMessage(CatalogError, "criteria_version"):
            load_criteria_version(path)
