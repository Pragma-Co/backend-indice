import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from classifier.catalog import FIELDS, CatalogError, load_catalog

VALID_CATALOG = {
    "discipline": ["EST", "MAT"],
    "document_type": ["DWG", "MEM"],
    "area": ["EST", "SIS"],
}


class LoadCatalogTests(SimpleTestCase):
    def write_catalog(self, content):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "catalog.json"
        path.write_text(content if isinstance(content, str) else json.dumps(content), "utf-8")
        return path

    def test_should_load_default_catalog_with_every_field(self):
        catalog = load_catalog()

        self.assertEqual(tuple(catalog), FIELDS)
        self.assertTrue(all(catalog[name] for name in FIELDS))

    def test_should_load_labels_as_sets_per_field(self):
        path = self.write_catalog(VALID_CATALOG)

        catalog = load_catalog(path)

        self.assertEqual(catalog["discipline"], frozenset({"EST", "MAT"}))
        self.assertEqual(catalog["area"], frozenset({"EST", "SIS"}))

    def test_should_reject_invalid_json(self):
        path = self.write_catalog("{not json")

        with self.assertRaises(CatalogError) as raised:
            load_catalog(path)

        self.assertIn("not valid JSON", str(raised.exception))

    def test_should_reject_catalog_missing_a_field(self):
        path = self.write_catalog({"discipline": ["EST"], "area": ["EST"]})

        with self.assertRaises(CatalogError) as raised:
            load_catalog(path)

        self.assertEqual(
            str(raised.exception), "document_type: expected a non-empty list of labels"
        )

    def test_should_reject_empty_label_list(self):
        path = self.write_catalog({**VALID_CATALOG, "area": []})

        with self.assertRaises(CatalogError) as raised:
            load_catalog(path)

        self.assertEqual(str(raised.exception), "area: expected a non-empty list of labels")

    def test_should_reject_label_with_surrounding_spaces(self):
        path = self.write_catalog({**VALID_CATALOG, "discipline": ["EST ", "MAT"]})

        with self.assertRaises(CatalogError) as raised:
            load_catalog(path)

        self.assertIn("discipline: labels must be non-blank", str(raised.exception))

    def test_should_reject_duplicated_labels(self):
        path = self.write_catalog({**VALID_CATALOG, "discipline": ["EST", "EST"]})

        with self.assertRaises(CatalogError) as raised:
            load_catalog(path)

        self.assertEqual(str(raised.exception), "discipline: duplicated labels")
