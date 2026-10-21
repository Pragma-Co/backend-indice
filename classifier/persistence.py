import hashlib
import json
import sys
import warnings
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import sklearn
import torch

from classifier import text_preprocessing, tfidf_input
from classifier.catalog import FIELDS
from classifier.evaluation import FieldEvaluation
from classifier.network import MultiHeadNetwork
from classifier.neural_training import TrainedNetwork
from classifier.splitting import RANDOM_STATE, TEST_FOLDS, VALIDATION_FOLDS

DEFAULT_OUTPUT_DIR = "classifier_artifacts"
METADATA_FILENAME = "metadata.json"
MODEL_FILENAME = "model.pt"
VECTORIZER_FILENAME = "vectorizer.joblib"
MODEL_TYPE = "multi_head_network"
INPUT_REPRESENTATION = "tfidf"


class ArtifactsError(Exception):
    pass


@dataclass
class LoadedModel:
    network: MultiHeadNetwork
    vectorizer: object
    classes: dict[str, list[str]]
    metadata: dict


def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_handling_sha256() -> str:
    digest = hashlib.sha256()
    for module in (text_preprocessing, tfidf_input):
        source = Path(module.__file__).read_text(encoding="utf-8")
        digest.update(source.replace("\r\n", "\n").encode("utf-8"))
    return digest.hexdigest()


def json_safe(value):
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def build_metadata(
    trained: TrainedNetwork,
    input_size: int,
    evaluations: dict[str, FieldEvaluation],
    dataset_path,
    catalog,
    criteria_version: str,
    row_count: int,
) -> dict:
    return {
        "model_type": MODEL_TYPE,
        "input_representation": INPUT_REPRESENTATION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "torch_version": torch.__version__,
        "scikit_learn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
        "dataset_sha256": file_sha256(dataset_path),
        "rows": row_count,
        "text_handling_sha256": text_handling_sha256(),
        "criteria_version": criteria_version,
        "catalog": {name: sorted(catalog[name]) for name in FIELDS},
        "input_size": input_size,
        "classes": trained.classes,
        "hyperparameters": asdict(trained.config),
        "best_epoch": trained.best_epoch,
        "epochs_run": len(trained.train_loss),
        "split": {
            "random_state": RANDOM_STATE,
            "test_folds": TEST_FOLDS,
            "validation_folds": VALIDATION_FOLDS,
        },
        "fields": {
            name: {
                "support": evaluations[name].support,
                "accuracy": evaluations[name].accuracy,
                "f1_macro": evaluations[name].f1_macro,
                "report": evaluations[name].report,
            }
            for name in FIELDS
        },
    }


def save_model(
    trained: TrainedNetwork,
    vectorizer,
    evaluations: dict[str, FieldEvaluation],
    dataset_path,
    catalog,
    criteria_version: str,
    row_count: int,
    output_dir=DEFAULT_OUTPUT_DIR,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(trained.network.state_dict(), directory / MODEL_FILENAME)
    joblib.dump(vectorizer, directory / VECTORIZER_FILENAME)
    input_size = len(vectorizer.vocabulary_)
    metadata = build_metadata(
        trained, input_size, evaluations, dataset_path, catalog, criteria_version, row_count
    )
    metadata["tfidf_token_pattern"] = vectorizer.token_pattern
    (directory / METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=json_safe) + "\n",
        encoding="utf-8",
    )
    return directory


def load_model(output_dir=DEFAULT_OUTPUT_DIR) -> LoadedModel:
    directory = Path(output_dir)
    metadata = _read_metadata(directory)

    if metadata.get("model_type") != MODEL_TYPE:
        raise ArtifactsError(
            f"The files in {directory} were not saved by the multi-head trainer; retrain the model"
        )
    if metadata["text_handling_sha256"] != text_handling_sha256():
        raise ArtifactsError(
            "The text handling changed since this model was trained; retrain the model"
        )
    if metadata["torch_version"] != torch.__version__:
        warnings.warn(
            f"Model trained with torch {metadata['torch_version']}, running {torch.__version__}",
            stacklevel=2,
        )

    model_path = _require_file(directory, MODEL_FILENAME)
    vectorizer_path = _require_file(directory, VECTORIZER_FILENAME)
    classes = metadata["classes"]
    hyperparameters = metadata["hyperparameters"]
    network = MultiHeadNetwork(
        metadata["input_size"],
        {name: len(classes[name]) for name in FIELDS},
        hidden_size=hyperparameters["hidden_size"],
        dropout=hyperparameters["dropout"],
    )
    network.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
    network.eval()
    return LoadedModel(
        network=network,
        vectorizer=joblib.load(vectorizer_path),
        classes=classes,
        metadata=metadata,
    )


def _read_metadata(directory: Path) -> dict:
    metadata_file = _require_file(directory, METADATA_FILENAME)
    return json.loads(metadata_file.read_text(encoding="utf-8"))


def _require_file(directory: Path, filename: str) -> Path:
    path = directory / filename
    if not path.is_file():
        raise ArtifactsError(f"File not found: {path}")
    return path
