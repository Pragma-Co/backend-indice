import torch
from torch import nn

HIDDEN_SIZE = 256
HEAD_HIDDEN_SIZE = 0
DROPOUT = 0.3


def build_head(shared_size: int, head_hidden_size: int, output_size: int, dropout: float):
    if head_hidden_size <= 0:
        return nn.Linear(shared_size, output_size)
    return nn.Sequential(
        nn.Linear(shared_size, head_hidden_size),
        nn.ReLU(),
        nn.Dropout(dropout),
        nn.Linear(head_hidden_size, output_size),
    )


class MultiHeadNetwork(nn.Module):
    def __init__(
        self,
        input_size: int,
        head_sizes: dict[str, int],
        hidden_size: int = HIDDEN_SIZE,
        dropout: float = DROPOUT,
        head_hidden_size: int = HEAD_HIDDEN_SIZE,
    ):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(input_size, hidden_size), nn.ReLU(), nn.Dropout(dropout)
        )
        self.heads = nn.ModuleDict(
            {
                name: build_head(hidden_size, head_hidden_size, size, dropout)
                for name, size in head_sizes.items()
            }
        )

    def forward(self, features: torch.Tensor) -> dict[str, torch.Tensor]:
        shared = self.trunk(features)
        return {name: head(shared) for name, head in self.heads.items()}

    def predict_probabilities(self, features: torch.Tensor) -> dict[str, torch.Tensor]:
        was_training = self.training
        self.eval()
        with torch.no_grad():
            logits = self(features)
        self.train(was_training)
        return {name: torch.softmax(values, dim=1) for name, values in logits.items()}
