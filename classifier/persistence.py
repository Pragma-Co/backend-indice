import hashlib
import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import joblib
import sklearn

from classifier import text_preprocessing
from classifier.catalog import FIELDS
from classifier.evaluation import FieldEvaluation
from classifier.training import RANDOM_STATE, TEST_SIZE, TrainedField

DEFAULT_OUTPUT_DIR = "classifier_artifacts"
METADATA_FILENAME = "metadata.json"


class ArtifactsError(Exception):
    pass


def model_path(output_dir, field: str) -> Path:
    return Path(output_dir) / f"{field}.joblib"


def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def preprocessing_sha256() -> str:
    source = Path(text_preprocessing.__file__).read_text(encoding="utf-8")
    return hashlib.sha256(source.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def json_safe(value):
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def build_metadata(trained, evaluations, csv_path, catalog) -> dict:
    first = next(iter(trained.values()))
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "scikit_learn_version": sklearn.__version__,
        "joblib_version": joblib.__version__,
        "csv_sha256": file_sha256(csv_path),
        "rows": first.train_size + len(first.test_labels),
        "random_state": RANDOM_STATE,
        "test_size": TEST_SIZE,
        "preprocessing_sha256": preprocessing_sha256(),
        "catalog": {name: sorted(catalog[name]) for name in FIELDS},
        "fields": {
            name: {
                "classes": evaluations[name].labels,
                "train_size": trained[name].train_size,
                "test_size": evaluations[name].support,
                "accuracy": evaluations[name].accuracy,
                "f1_macro": evaluations[name].f1_macro,
                "report": evaluations[name].report,
            }
            for name in FIELDS
        },
    }


def save_models(
    trained: dict[str, TrainedField],
    evaluations: dict[str, FieldEvaluation],
    output_dir,
    csv_path,
    catalog,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for name in FIELDS:
        joblib.dump(trained[name].pipeline, model_path(directory, name))
    metadata = build_metadata(trained, evaluations, csv_path, catalog)
    (directory / METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=json_safe) + "\n",
        encoding="utf-8",
    )
    return directory


def load_models(output_dir=DEFAULT_OUTPUT_DIR):
    directory = Path(output_dir)
    metadata_file = directory / METADATA_FILENAME
    if not metadata_file.is_file():
        raise ArtifactsError(f"No {METADATA_FILENAME} found in {directory}")
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

    if metadata["preprocessing_sha256"] != preprocessing_sha256():
        raise ArtifactsError(
            "The text preprocessing changed since these models were trained; retrain them"
        )
    if metadata["scikit_learn_version"] != sklearn.__version__:
        warnings.warn(
            f"Models trained with scikit-learn {metadata['scikit_learn_version']}, "
            f"running {sklearn.__version__}",
            stacklevel=2,
        )

    models = {}
    for name in FIELDS:
        path = model_path(directory, name)
        if not path.is_file():
            raise ArtifactsError(f"Model file not found: {path}")
        models[name] = joblib.load(path)
    return models, metadata
