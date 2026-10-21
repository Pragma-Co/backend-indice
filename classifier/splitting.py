from dataclasses import dataclass

from sklearn.model_selection import StratifiedGroupKFold

from classifier.catalog import FIELDS
from classifier.dataset import Dataset

RANDOM_STATE = 42
TEST_FOLDS = 5
VALIDATION_FOLDS = 5
STRATIFY_FIELD = "discipline"


class SplitError(Exception):
    pass


@dataclass
class Split:
    train: list[int]
    validation: list[int]
    test: list[int]

    def named_sets(self) -> dict[str, list[int]]:
        return {"train": self.train, "validation": self.validation, "test": self.test}


def _hold_out_one_fold(
    indices: list[int], labels: list[str], groups: list[str], folds: int, random_state: int
) -> tuple[list[int], list[int]]:
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=random_state)
    try:
        kept, held_out = next(
            iter(
                splitter.split(
                    indices,
                    [labels[index] for index in indices],
                    [groups[index] for index in indices],
                )
            )
        )
    except ValueError as exc:
        raise SplitError(f"could not split the dataset: {exc}") from exc
    return [indices[position] for position in kept], [indices[position] for position in held_out]


def split_dataset(dataset: Dataset, random_state: int = RANDOM_STATE) -> Split:
    indices = list(range(len(dataset.texts)))
    labels = dataset.labels[STRATIFY_FIELD]

    train_and_validation, test = _hold_out_one_fold(
        indices, labels, dataset.groups, TEST_FOLDS, random_state
    )
    train, validation = _hold_out_one_fold(
        train_and_validation, labels, dataset.groups, VALIDATION_FOLDS, random_state
    )

    split = Split(train=sorted(train), validation=sorted(validation), test=sorted(test))
    _require_every_class_in_every_set(dataset, split)
    return split


def _require_every_class_in_every_set(dataset: Dataset, split: Split) -> None:
    missing = []
    for field_name in FIELDS:
        classes = sorted(set(dataset.labels[field_name]))
        for set_name, indices in split.named_sets().items():
            present = {dataset.labels[field_name][index] for index in indices}
            missing.extend(
                f"{field_name}: class {label} has no example in the {set_name} set"
                for label in classes
                if label not in present
            )
    if missing:
        raise SplitError("; ".join(missing))
