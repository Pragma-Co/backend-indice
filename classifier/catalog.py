import json
from pathlib import Path

FIELDS = ("discipline", "document_type", "area")
DEFAULT_CATALOG_PATH = Path(__file__).with_name("catalog.json")


class CatalogError(Exception):
    pass


def load_catalog(path=DEFAULT_CATALOG_PATH) -> dict[str, frozenset[str]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"The catalog is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise CatalogError("The catalog must be a JSON object keyed by field")

    catalog = {}
    for name in FIELDS:
        labels = data.get(name)
        if not isinstance(labels, list) or not labels:
            raise CatalogError(f"{name}: expected a non-empty list of labels")
        if not all(isinstance(label, str) and label.strip() == label and label for label in labels):
            raise CatalogError(
                f"{name}: labels must be non-blank strings without surrounding spaces"
            )
        if len(set(labels)) != len(labels):
            raise CatalogError(f"{name}: duplicated labels")
        catalog[name] = frozenset(labels)
    return catalog
