from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from classifier.catalog import FIELDS
from classifier.dataset import Dataset
from classifier.splitting import Split
from classifier.text_preprocessing import preprocess_for_llm
from classifier.tfidf_input import MIN_DOCUMENT_FREQUENCY, NGRAM_RANGE

MAX_ITERATIONS = 1000


def build_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    preprocessor=preprocess_for_llm,
                    ngram_range=NGRAM_RANGE,
                    min_df=MIN_DOCUMENT_FREQUENCY,
                    sublinear_tf=True,
                ),
            ),
            ("classifier", LogisticRegression(max_iter=MAX_ITERATIONS, class_weight="balanced")),
        ]
    )


def train_baseline(dataset: Dataset, split: Split) -> dict[str, Pipeline]:
    train_texts = [dataset.texts[index] for index in split.train]
    pipelines = {}
    for name in FIELDS:
        train_labels = [dataset.labels[name][index] for index in split.train]
        pipeline = build_pipeline()
        pipeline.fit(train_texts, train_labels)
        pipelines[name] = pipeline
    return pipelines


def predict_baseline(pipelines: dict[str, Pipeline], texts: list[str]) -> dict[str, list[str]]:
    return {name: [str(label) for label in pipelines[name].predict(texts)] for name in FIELDS}
