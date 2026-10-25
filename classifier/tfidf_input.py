from sklearn.feature_extraction.text import TfidfVectorizer

from classifier.text_preprocessing import preprocess_for_llm

NGRAM_RANGE = (1, 2)
MIN_DOCUMENT_FREQUENCY = 2
MAX_FEATURES = 20000
DEFAULT_TOKEN_PATTERN = r"(?u)\b\w\w+\b"
WORDS_OR_NUMBERS_PATTERN = r"(?u)\b(?:[^\W\d_]{2,}|\d{2,})\b"


def build_vectorizer(
    max_features: int = MAX_FEATURES, filter_noise: bool = False
) -> TfidfVectorizer:
    return TfidfVectorizer(
        preprocessor=preprocess_for_llm,
        ngram_range=NGRAM_RANGE,
        min_df=MIN_DOCUMENT_FREQUENCY,
        max_features=max_features,
        sublinear_tf=True,
        token_pattern=WORDS_OR_NUMBERS_PATTERN if filter_noise else DEFAULT_TOKEN_PATTERN,
    )
