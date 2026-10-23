import copy
from dataclasses import dataclass

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn

from classifier.catalog import FIELDS
from classifier.network import DROPOUT, HIDDEN_SIZE, MultiHeadNetwork

RANDOM_STATE = 42
MINIMUM_IMPROVEMENT = 1e-9


@dataclass
class TrainingConfig:
    hidden_size: int = HIDDEN_SIZE
    dropout: float = DROPOUT
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    batch_size: int = 32
    max_epochs: int = 200
    patience: int = 15
    random_state: int = RANDOM_STATE


@dataclass
class TrainedNetwork:
    network: MultiHeadNetwork
    classes: dict[str, list[str]]
    config: TrainingConfig
    train_loss: list[float]
    validation_f1: list[float]
    best_epoch: int


def to_tensor(features) -> torch.Tensor:
    dense = features.toarray() if hasattr(features, "toarray") else np.asarray(features)
    return torch.tensor(dense, dtype=torch.float32)


def encode_labels(
    labels: dict[str, list[str]], classes: dict[str, list[str]]
) -> dict[str, torch.Tensor]:
    return {
        name: torch.tensor([classes[name].index(label) for label in labels[name]], dtype=torch.long)
        for name in FIELDS
    }


def balanced_class_weights(targets: torch.Tensor, class_count: int) -> torch.Tensor:
    counts = torch.bincount(targets, minlength=class_count).float()
    weights = torch.zeros(class_count)
    present = counts > 0
    weights[present] = len(targets) / (class_count * counts[present])
    return weights


def macro_f1_mean(
    network: MultiHeadNetwork, features: torch.Tensor, targets: dict[str, torch.Tensor]
) -> float:
    probabilities = network.predict_probabilities(features)
    scores = []
    for name in FIELDS:
        predicted = probabilities[name].argmax(dim=1).numpy()
        scores.append(
            f1_score(
                targets[name].numpy(),
                predicted,
                labels=list(range(probabilities[name].shape[1])),
                average="macro",
                zero_division=0,
            )
        )
    return float(np.mean(scores))


def train_network(
    train_features,
    train_labels: dict[str, list[str]],
    validation_features,
    validation_labels: dict[str, list[str]],
    config: TrainingConfig | None = None,
) -> TrainedNetwork:
    config = config or TrainingConfig()
    classes = {
        name: sorted(set(train_labels[name]) | set(validation_labels[name])) for name in FIELDS
    }
    train_x = to_tensor(train_features)
    validation_x = to_tensor(validation_features)
    train_y = encode_labels(train_labels, classes)
    validation_y = encode_labels(validation_labels, classes)

    torch.manual_seed(config.random_state)
    generator = torch.Generator().manual_seed(config.random_state)
    network = MultiHeadNetwork(
        train_x.shape[1],
        {name: len(classes[name]) for name in FIELDS},
        hidden_size=config.hidden_size,
        dropout=config.dropout,
    )
    optimizer = torch.optim.Adam(
        network.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    losses = {
        name: nn.CrossEntropyLoss(weight=balanced_class_weights(train_y[name], len(classes[name])))
        for name in FIELDS
    }

    sample_count = train_x.shape[0]
    train_loss, validation_f1 = [], []
    best_f1, best_epoch, best_state = -1.0, 0, copy.deepcopy(network.state_dict())
    epochs_without_improvement = 0

    for epoch in range(config.max_epochs):
        network.train()
        order = torch.randperm(sample_count, generator=generator)
        epoch_loss = 0.0
        for start in range(0, sample_count, config.batch_size):
            batch = order[start : start + config.batch_size]
            optimizer.zero_grad()
            outputs = network(train_x[batch])
            loss = sum(losses[name](outputs[name], train_y[name][batch]) for name in FIELDS)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * len(batch)
        train_loss.append(epoch_loss / sample_count)

        score = macro_f1_mean(network, validation_x, validation_y)
        validation_f1.append(score)
        if score > best_f1 + MINIMUM_IMPROVEMENT:
            best_f1, best_epoch = score, epoch
            best_state = copy.deepcopy(network.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.patience:
                break

    network.load_state_dict(best_state)
    network.eval()
    return TrainedNetwork(
        network=network,
        classes=classes,
        config=config,
        train_loss=train_loss,
        validation_f1=validation_f1,
        best_epoch=best_epoch,
    )
