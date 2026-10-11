from dataclasses import dataclass

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from classifier.catalog import FIELDS
from classifier.dataset import Dataset
from classifier.pipeline import build_pipeline

RANDOM_STATE = 42
TEST_SIZE = 0.2


class TrainingError(Exception):
    pass


@dataclass
class TrainedField:
    name: str
    pipeline: Pipeline
    train_size: int
    test_texts: list[str]
    test_labels: list[str]


def train_field(
    name: str,
    texts: list[str],
    labels: list[str],
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
) -> TrainedField:
    try:
        train_texts, test_texts, train_labels, test_labels = train_test_split(
            texts,
            labels,
            test_size=test_size,
            random_state=random_state,
            stratify=labels,
        )
    except ValueError as exc:
        raise TrainingError(f"{name}: could not split the dataset: {exc}") from exc

    pipeline = build_pipeline()
    pipeline.fit(train_texts, train_labels)
    return TrainedField(
        name=name,
        pipeline=pipeline,
        train_size=len(train_texts),
        test_texts=test_texts,
        test_labels=test_labels,
    )


def train_all(dataset: Dataset) -> dict[str, TrainedField]:
    return {name: train_field(name, dataset.texts, dataset.labels[name]) for name in FIELDS}
