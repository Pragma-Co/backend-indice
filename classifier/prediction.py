from dataclasses import dataclass
from functools import cache

from classifier.catalog import FIELDS
from classifier.neural_training import to_tensor
from classifier.persistence import DEFAULT_OUTPUT_DIR, load_model


@dataclass
class Prediction:
    label: str
    confidence: float


class Classifier:
    def __init__(self, output_dir=DEFAULT_OUTPUT_DIR):
        loaded = load_model(output_dir)
        self.network = loaded.network
        self.vectorizer = loaded.vectorizer
        self.classes = loaded.classes
        self.metadata = loaded.metadata

    def predict(self, text: str) -> dict[str, Prediction]:
        if not text.strip():
            raise ValueError("text must not be empty")

        features = to_tensor(self.vectorizer.transform([text]))
        probabilities = self.network.predict_probabilities(features)

        predictions = {}
        for name in FIELDS:
            values = probabilities[name][0]
            best = int(values.argmax())
            predictions[name] = Prediction(
                label=self.classes[name][best], confidence=float(values[best])
            )
        return predictions


@cache
def get_classifier(output_dir=DEFAULT_OUTPUT_DIR) -> Classifier:
    return Classifier(output_dir)
