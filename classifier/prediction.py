from dataclasses import dataclass
from functools import cache

from classifier.persistence import DEFAULT_OUTPUT_DIR, load_models


@dataclass
class Prediction:
    label: str
    confidence: float


class Classifier:
    def __init__(self, output_dir=DEFAULT_OUTPUT_DIR):
        self.models, self.metadata = load_models(output_dir)

    def predict(self, text: str) -> dict[str, Prediction]:
        if not text.strip():
            raise ValueError("text must not be empty")

        predictions = {}
        for name, model in self.models.items():
            probabilities = model.predict_proba([text])[0]
            best = int(probabilities.argmax())
            predictions[name] = Prediction(
                label=str(model.classes_[best]), confidence=float(probabilities[best])
            )
        return predictions


@cache
def get_classifier(output_dir=DEFAULT_OUTPUT_DIR) -> Classifier:
    return Classifier(output_dir)
