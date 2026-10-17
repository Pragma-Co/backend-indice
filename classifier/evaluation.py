from dataclasses import dataclass

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from classifier.training import TrainedField


@dataclass
class FieldEvaluation:
    name: str
    support: int
    accuracy: float
    f1_macro: float
    report_text: str
    report: dict
    labels: list[str]
    confusion_matrix: list[list[int]]


def evaluate_field(trained: TrainedField) -> FieldEvaluation:
    labels = [str(label) for label in trained.pipeline.classes_]
    expected = trained.test_labels
    predicted = list(trained.pipeline.predict(trained.test_texts))

    return FieldEvaluation(
        name=trained.name,
        support=len(expected),
        accuracy=float(accuracy_score(expected, predicted)),
        f1_macro=float(
            f1_score(expected, predicted, labels=labels, average="macro", zero_division=0)
        ),
        report_text=classification_report(
            expected, predicted, labels=labels, zero_division=0, digits=3
        ),
        report=classification_report(
            expected, predicted, labels=labels, zero_division=0, output_dict=True
        ),
        labels=labels,
        confusion_matrix=confusion_matrix(expected, predicted, labels=labels).tolist(),
    )


def evaluate_all(trained_fields: dict[str, TrainedField]) -> dict[str, FieldEvaluation]:
    return {name: evaluate_field(trained) for name, trained in trained_fields.items()}


def format_confusion_matrix(labels: list[str], matrix: list[list[int]]) -> str:
    width = max(
        [len(label) for label in labels] + [len(str(value)) for row in matrix for value in row]
    )
    header = " " * width + "".join(f"  {label:>{width}}" for label in labels)
    rows = [
        f"{label:<{width}}" + "".join(f"  {value:>{width}}" for value in row)
        for label, row in zip(labels, matrix, strict=True)
    ]
    return "\n".join([header, *rows])


def format_evaluation(evaluation: FieldEvaluation, train_size: int) -> str:
    return "\n".join(
        [
            f"== {evaluation.name} (trained on {train_size}, tested on {evaluation.support}) ==",
            f"accuracy: {evaluation.accuracy:.3f}",
            f"f1 macro: {evaluation.f1_macro:.3f}",
            "",
            evaluation.report_text.rstrip(),
            "",
            "confusion matrix (rows = true label, columns = predicted label):",
            format_confusion_matrix(evaluation.labels, evaluation.confusion_matrix),
        ]
    )
