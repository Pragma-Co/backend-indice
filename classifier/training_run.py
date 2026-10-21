from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer

from classifier.catalog import FIELDS
from classifier.dataset import Dataset
from classifier.evaluation import FieldEvaluation, evaluate_fields
from classifier.neural_training import (
    RANDOM_STATE,
    TrainedNetwork,
    TrainingConfig,
    to_tensor,
    train_network,
)
from classifier.splitting import Split, split_dataset
from classifier.tfidf_input import MAX_FEATURES, build_vectorizer


@dataclass
class StoredFeatures:
    vectorizer: TfidfVectorizer
    features: object


@dataclass
class TrainingRun:
    trained: TrainedNetwork
    vectorizer: TfidfVectorizer
    split: Split
    evaluations: dict[str, FieldEvaluation]


def _rows(values: list, indices: list[int]) -> list:
    return [values[index] for index in indices]


def run_training(
    dataset: Dataset,
    config: TrainingConfig | None = None,
    max_features: int = MAX_FEATURES,
    random_state: int = RANDOM_STATE,
    stored: StoredFeatures | None = None,
    filter_noise: bool = False,
) -> TrainingRun:
    split = split_dataset(dataset, random_state)
    if stored:
        vectorizer = stored.vectorizer
        train_features = stored.features[split.train]
        validation_features = stored.features[split.validation]
        test_features = stored.features[split.test]
    else:
        vectorizer = build_vectorizer(max_features, filter_noise)
        train_features = vectorizer.fit_transform(_rows(dataset.texts, split.train))
        validation_features = vectorizer.transform(_rows(dataset.texts, split.validation))
        test_features = vectorizer.transform(_rows(dataset.texts, split.test))

    def labels_for(indices: list[int]) -> dict[str, list[str]]:
        return {name: _rows(dataset.labels[name], indices) for name in FIELDS}

    trained = train_network(
        train_features,
        labels_for(split.train),
        validation_features,
        labels_for(split.validation),
        config,
    )
    probabilities = trained.network.predict_probabilities(to_tensor(test_features))
    predicted = {
        name: [trained.classes[name][int(best)] for best in probabilities[name].argmax(dim=1)]
        for name in FIELDS
    }
    evaluations = evaluate_fields(labels_for(split.test), predicted, trained.classes)
    return TrainingRun(trained=trained, vectorizer=vectorizer, split=split, evaluations=evaluations)
