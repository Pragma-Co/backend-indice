import numpy as np
import torch
from django.test import SimpleTestCase

from classifier.neural_training import (
    TrainingConfig,
    balanced_class_weights,
    train_network,
)

CLASSES = {
    "discipline": ["MECHANICAL", "ELECTRICAL", "MATERIALS"],
    "document_type": ["SPECIFICATION", "STANDARD", "HANDBOOK", "COMMERCIAL_ITEM"],
    "area": ["DESIGN", "MATERIALS", "PROCESSING"],
}
FIELD_NAMES = list(CLASSES)


def synthetic_data(sample_count: int, seed: int):
    rng = np.random.default_rng(seed)
    labels = {
        name: [CLASSES[name][index % len(CLASSES[name])] for index in range(sample_count)]
        for name in FIELD_NAMES
    }
    columns = []
    for name in FIELD_NAMES:
        one_hot = np.zeros((sample_count, len(CLASSES[name])))
        for row, label in enumerate(labels[name]):
            one_hot[row, CLASSES[name].index(label)] = 3.0
        columns.append(one_hot)
    features = np.hstack(columns) + rng.normal(0, 0.3, (sample_count, sum(map(len, CLASSES.values()))))
    return features, labels


class TrainNetworkTests(SimpleTestCase):
    def train(self, **config):
        train_x, train_y = synthetic_data(160, seed=1)
        validation_x, validation_y = synthetic_data(48, seed=2)
        return train_network(
            train_x, train_y, validation_x, validation_y, TrainingConfig(max_epochs=60, **config)
        )

    def test_should_reduce_the_training_loss(self):
        trained = self.train()

        self.assertLess(trained.train_loss[-1], trained.train_loss[0] / 2)

    def test_should_learn_all_three_fields_from_a_separable_signal(self):
        trained = self.train()

        self.assertGreater(max(trained.validation_f1), 0.9)

    def test_should_return_one_probability_distribution_per_field(self):
        trained = self.train()
        features, _ = synthetic_data(5, seed=3)

        probabilities = trained.network.predict_probabilities(
            torch.tensor(features, dtype=torch.float32)
        )

        self.assertEqual(set(probabilities), set(FIELD_NAMES))
        for name, values in probabilities.items():
            self.assertEqual(values.shape, (5, len(CLASSES[name])))
            self.assertTrue(torch.allclose(values.sum(dim=1), torch.ones(5)))

    def test_should_stop_early_and_restore_the_best_epoch(self):
        trained = self.train(patience=3)

        self.assertLess(len(trained.validation_f1), 60)
        self.assertEqual(trained.validation_f1[trained.best_epoch], max(trained.validation_f1))

    def test_should_repeat_the_same_history_with_the_same_seed(self):
        first = self.train()
        second = self.train()

        self.assertEqual(first.train_loss, second.train_loss)


class BalancedClassWeightsTests(SimpleTestCase):
    def test_should_weigh_a_rare_class_above_a_common_one(self):
        targets = torch.tensor([0, 0, 0, 0, 0, 0, 1, 1, 2])

        weights = balanced_class_weights(targets, class_count=3)

        self.assertGreater(weights[2], weights[1])
        self.assertGreater(weights[1], weights[0])

    def test_should_give_no_weight_to_a_class_without_examples(self):
        weights = balanced_class_weights(torch.tensor([0, 0, 1]), class_count=3)

        self.assertEqual(weights[2].item(), 0.0)
