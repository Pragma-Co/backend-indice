import json
from pathlib import Path

FIELDS = ("discipline", "document_type", "area")
DEFAULT_CATALOG_PATH = Path(__file__).with_name("catalog.json")
CRITERIA_VERSION_KEY = "criteria_version"
AREA_STAGES_KEY = "area_stages"
AREA_GROUPS_KEY = "area_groups"
DOCUMENT_TYPES = frozenset({"STANDARD", "HANDBOOK", "SPECIFICATION", "COMMERCIAL_ITEM"})


class CatalogError(Exception):
    pass


def _read_catalog_file(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"The catalog is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise CatalogError("The catalog must be a JSON object keyed by field")
    return data


def load_catalog(path=DEFAULT_CATALOG_PATH) -> dict[str, frozenset[str]]:
    data = _read_catalog_file(path)

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

    if catalog["document_type"] != DOCUMENT_TYPES:
        raise CatalogError(f"document_type: expected exactly {sorted(DOCUMENT_TYPES)}")
    return catalog


def _load_area_mapping(path) -> tuple[frozenset[str], dict[str, str]]:
    data = _read_catalog_file(path)
    stages = data.get(AREA_STAGES_KEY)
    groups = data.get(AREA_GROUPS_KEY)
    if not isinstance(stages, list) or not stages or len(set(stages)) != len(stages):
        raise CatalogError(f"{AREA_STAGES_KEY}: expected a non-empty list without duplicates")
    if not isinstance(groups, dict) or set(groups) != set(stages):
        raise CatalogError(f"{AREA_GROUPS_KEY}: expected one entry for each of the stages")
    if set(groups.values()) != set(load_catalog(path)["area"]):
        raise CatalogError(f"{AREA_GROUPS_KEY}: must map the stages onto exactly the area classes")
    return frozenset(stages), dict(groups)


def load_area_stages(path=DEFAULT_CATALOG_PATH) -> frozenset[str]:
    return _load_area_mapping(path)[0]


def load_area_groups(path=DEFAULT_CATALOG_PATH) -> dict[str, str]:
    return _load_area_mapping(path)[1]


def load_criteria_version(path=DEFAULT_CATALOG_PATH) -> str:
    version = _read_catalog_file(path).get(CRITERIA_VERSION_KEY)
    if not isinstance(version, str) or not version.strip():
        raise CatalogError(f"{CRITERIA_VERSION_KEY}: expected a non-blank string")
    return version
