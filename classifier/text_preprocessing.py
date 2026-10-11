import re
from functools import lru_cache

import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

NLTK_RESOURCES = {
    "stopwords": "corpora/stopwords",
    "punkt": "tokenizers/punkt",
    "punkt_tab": "tokenizers/punkt_tab",
    "wordnet": "corpora/wordnet",
    "omw-1.4": "corpora/omw-1.4",
}


@lru_cache(maxsize=1)
def _ensure_nltk_resources() -> None:
    for package, resource_path in NLTK_RESOURCES.items():
        try:
            nltk.data.find(resource_path)
        except LookupError:
            nltk.download(package, quiet=True)


@lru_cache(maxsize=1)
def _english_stop_words() -> frozenset[str]:
    _ensure_nltk_resources()
    return frozenset(stopwords.words("english"))


@lru_cache(maxsize=1)
def _lemmatizer() -> WordNetLemmatizer:
    _ensure_nltk_resources()
    return WordNetLemmatizer()


def clean_and_normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\n", " ").replace("\f", " ")
    return text.lower().strip()


def preprocess_for_llm(text: str) -> str:
    _ensure_nltk_resources()

    text = clean_and_normalize_text(text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"[\W_]+", " ", text)

    words = word_tokenize(text)
    stop_words = _english_stop_words()
    words = [word for word in words if word not in stop_words]

    lemmatizer = _lemmatizer()
    words = [lemmatizer.lemmatize(word) for word in words]

    return " ".join(words)
