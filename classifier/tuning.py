import argparse
import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from classifier.catalog import DEFAULT_CATALOG_PATH, FIELDS, CatalogError, load_catalog
from classifier.dataset import Dataset, DatasetValidationError, load_dataset
from classifier.evaluation import evaluate_fields
from classifier.neural_training import TrainingConfig, to_tensor, train_network
from classifier.splitting import SplitError, split_dataset
from classifier.tfidf_input import MAX_FEATURES, build_vectorizer

DEFAULT_LABEL = "default"


@dataclass(frozen=True)
class Trial:
    label: str
    config: TrainingConfig
    filter_noise: bool = False


@dataclass
class TrialResult:
    label: str
    config: TrainingConfig
    filter_noise: bool
    validation_f1: dict[str, float]
    mean_f1: float
    best_epoch: int


def default_grid(base: TrainingConfig | None = None) -> list[Trial]:
    base = base or TrainingConfig()
    trials = [Trial(DEFAULT_LABEL, base)]
    for weight_decay in (1e-5, 1e-3):
        trials.append(Trial(f"weight_decay={weight_decay:g}", replace(base, weight_decay=weight_decay)))
    for dropout in (0.2, 0.5):
        trials.append(Trial(f"dropout={dropout:g}", replace(base, dropout=dropout)))
    trials.append(Trial("filter_noise", base, filter_noise=True))
    return trials


def run_trial(dataset: Dataset, trial: Trial, max_features: int = MAX_FEATURES) -> TrialResult:
    split = split_dataset(dataset, trial.config.random_state)
    vectorizer = build_vectorizer(max_features, trial.filter_noise)
    train_features = vectorizer.fit_transform([dataset.texts[i] for i in split.train])
    validation_features = vectorizer.transform([dataset.texts[i] for i in split.validation])

    def labels_for(indices: list[int]) -> dict[str, list[str]]:
        return {name: [dataset.labels[name][i] for i in indices] for name in FIELDS}

    trained = train_network(
        train_features,
        labels_for(split.train),
        validation_features,
        labels_for(split.validation),
        trial.config,
    )
    probabilities = trained.network.predict_probabilities(to_tensor(validation_features))
    predicted = {
        name: [trained.classes[name][int(best)] for best in probabilities[name].argmax(dim=1)]
        for name in FIELDS
    }
    evaluations = evaluate_fields(labels_for(split.validation), predicted, trained.classes)
    validation_f1 = {name: evaluations[name].f1_macro for name in FIELDS}
    return TrialResult(
        label=trial.label,
        config=trial.config,
        filter_noise=trial.filter_noise,
        validation_f1=validation_f1,
        mean_f1=sum(validation_f1.values()) / len(FIELDS),
        best_epoch=trained.best_epoch,
    )


def run_tuning(
    dataset: Dataset, trials: list[Trial] | None = None, max_features: int = MAX_FEATURES
) -> list[TrialResult]:
    return [run_trial(dataset, trial, max_features) for trial in trials or default_grid()]


def best_result(results: list[TrialResult]) -> TrialResult:
    return max(results, key=lambda result: (result.mean_f1, result.label == DEFAULT_LABEL))


def format_table(results: list[TrialResult]) -> str:
    width = max(len(result.label) for result in results)
    header = f"{'trial':<{width}}  " + "  ".join(f"{name:>13}" for name in FIELDS) + "  mean   epoch"
    lines = [header]
    for result in results:
        values = "  ".join(f"{result.validation_f1[name]:>13.3f}" for name in FIELDS)
        lines.append(f"{result.label:<{width}}  {values}  {result.mean_f1:.3f}  {result.best_epoch:>5}")
    best = best_result(results)
    lines.append(f"best on validation: {best.label} (mean macro F1 {best.mean_f1:.3f})")
    return "\n".join(lines)


def to_json(results: list[TrialResult]) -> str:
    payload = [{**asdict(result), "config": asdict(result.config)} for result in results]
    return json.dumps(payload, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m classifier.tune")
    parser.add_argument("--csv", required=True, help="Training dataset (UTF-8 CSV).")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--max-features", type=int, default=MAX_FEATURES)
    parser.add_argument("--output", default=None, help="JSON file that receives every trial.")
    return parser


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        dataset = load_dataset(arguments.csv, load_catalog(arguments.catalog))
        results = run_tuning(dataset, max_features=arguments.max_features)
    except (CatalogError, DatasetValidationError, SplitError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(format_table(results))
    if arguments.output:
        Path(arguments.output).write_text(to_json(results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
