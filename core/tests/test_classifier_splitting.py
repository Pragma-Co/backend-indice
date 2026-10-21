from django.test import SimpleTestCase

from classifier.dataset import Dataset, DatasetReport
from classifier.splitting import SplitError, split_dataset

DISCIPLINES = ["MECHANICAL", "ELECTRICAL", "MATERIALS"]
DOCUMENT_TYPES = ["SPECIFICATION", "STANDARD", "HANDBOOK", "COMMERCIAL_ITEM"]
AREAS = ["DESIGN", "MATERIALS", "PROCESSING", "INSPECTION_TEST", "PACKAGING_STORAGE", "NO_CLEAR_STAGE"]


def build_dataset(group_count: int = 120, rows_per_group: int = 2) -> Dataset:
    texts, groups = [], []
    labels = {"discipline": [], "document_type": [], "area": []}
    for group_index in range(group_count):
        for revision in range(rows_per_group):
            texts.append(f"document {group_index} revision {revision}")
            groups.append(f"DOC-{group_index}")
            labels["discipline"].append(DISCIPLINES[group_index % len(DISCIPLINES)])
            labels["document_type"].append(DOCUMENT_TYPES[group_index % len(DOCUMENT_TYPES)])
            labels["area"].append(AREAS[group_index % len(AREAS)])
    return Dataset(texts=texts, labels=labels, groups=groups, report=DatasetReport())


class SplitDatasetTests(SimpleTestCase):
    def test_should_partition_every_row_into_exactly_one_set(self):
        dataset = build_dataset()

        split = split_dataset(dataset)

        merged = split.train + split.validation + split.test
        self.assertEqual(sorted(merged), list(range(len(dataset.texts))))

    def test_should_keep_every_revision_of_a_document_in_the_same_set(self):
        dataset = build_dataset()

        split = split_dataset(dataset)

        set_by_group = {}
        for set_name, indices in split.named_sets().items():
            for index in indices:
                set_by_group.setdefault(dataset.groups[index], set()).add(set_name)
        self.assertTrue(all(len(names) == 1 for names in set_by_group.values()))

    def test_should_produce_the_same_split_for_the_same_data_and_seed(self):
        dataset = build_dataset()

        first = split_dataset(dataset, random_state=7)
        second = split_dataset(dataset, random_state=7)

        self.assertEqual(first, second)

    def test_should_reserve_about_a_fifth_of_the_rows_for_testing(self):
        dataset = build_dataset()

        split = split_dataset(dataset)

        share = len(split.test) / len(dataset.texts)
        self.assertTrue(0.15 <= share <= 0.25)

    def test_should_fail_naming_the_class_that_disappears_from_a_set(self):
        dataset = build_dataset()
        dataset.labels["document_type"][0] = "UNCOMMON"
        dataset.labels["document_type"][1] = "UNCOMMON"

        with self.assertRaises(SplitError) as raised:
            split_dataset(dataset)

        self.assertIn("document_type: class UNCOMMON has no example in the", str(raised.exception))

    def test_should_fail_when_there_are_fewer_groups_than_folds(self):
        dataset = build_dataset(group_count=3)

        with self.assertRaises(SplitError):
            split_dataset(dataset)
