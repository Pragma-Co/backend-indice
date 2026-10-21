from classifier.catalog import FIELDS
from classifier.dataset import Dataset, DatasetReport

KEYWORDS = {
    "discipline": {"MECHANICAL": "bearing", "ELECTRICAL": "voltage", "MATERIALS": "alloy"},
    "document_type": {
        "SPECIFICATION": "shall",
        "STANDARD": "practice",
        "HANDBOOK": "guidance",
        "COMMERCIAL_ITEM": "purchase",
    },
    "area": {"DESIGN": "drawing", "MATERIALS": "composition", "OTHER_STAGE": "welding"},
}


def keyword_dataset(group_count: int = 120) -> Dataset:
    texts, groups = [], []
    labels = {name: [] for name in FIELDS}
    for group_index in range(group_count):
        chosen = {
            "discipline": sorted(KEYWORDS["discipline"])[group_index % 3],
            "document_type": sorted(KEYWORDS["document_type"])[(group_index // 3) % 4],
            "area": sorted(KEYWORDS["area"])[(group_index // 12) % 3],
        }
        for revision in range(2):
            words = " ".join(KEYWORDS[name][label] for name, label in chosen.items())
            texts.append(f"{words} {words} requirement document {group_index} {revision}")
            groups.append(f"DOC-{group_index}")
            for name, label in chosen.items():
                labels[name].append(label)
    return Dataset(texts=texts, labels=labels, groups=groups, report=DatasetReport())
