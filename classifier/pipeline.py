from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from classifier.text_preprocessing import preprocess_for_llm

NGRAM_RANGE = (1, 2)
MIN_DOCUMENT_FREQUENCY = 2
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
            ("classifier", LogisticRegression(max_iter=MAX_ITERATIONS)),
        ]
    )
