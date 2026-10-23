import hashlib
import json
from datetime import UTC, datetime

import numpy as np
from scipy.sparse import csr_matrix

COLLECTION_NAME = "document_vectors"
IDF_DECIMALS = 6


class VectorStoreError(Exception):
    pass


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def vectorizer_version(vectorizer) -> str:
    vocabulary = sorted((term, int(index)) for term, index in vectorizer.vocabulary_.items())
    idf = [round(float(weight), IDF_DECIMALS) for weight in vectorizer.idf_]
    parameters = {
        "ngram_range": list(vectorizer.ngram_range),
        "min_df": vectorizer.min_df,
        "max_features": vectorizer.max_features,
        "sublinear_tf": vectorizer.sublinear_tf,
        "token_pattern": vectorizer.token_pattern,
    }
    payload = json.dumps([vocabulary, idf, parameters], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class VectorStore:
    def __init__(self, collection):
        self.collection = collection

    def save_all(self, texts: list[str], features, version: str) -> int:
        rows = csr_matrix(features)
        if rows.shape[0] != len(texts):
            raise VectorStoreError(f"{len(texts)} texts for {rows.shape[0]} vectors")
        saved_at = datetime.now(UTC).isoformat(timespec="seconds")
        for position, text in enumerate(texts):
            row = rows.getrow(position)
            record = {
                "_id": text_sha256(text),
                "vectorizer_version": version,
                "dimension": int(rows.shape[1]),
                "indices": [int(index) for index in row.indices],
                "values": [float(value) for value in row.data],
                "saved_at": saved_at,
            }
            self.collection.replace_one({"_id": record["_id"]}, record, upsert=True)
        return len(texts)

    def load(self, texts: list[str], version: str) -> csr_matrix:
        keys = [text_sha256(text) for text in texts]
        found = {
            record["_id"]: record
            for record in self.collection.find({"_id": {"$in": keys}})
            if record.get("vectorizer_version") == version
        }
        missing = [key for key in keys if key not in found]
        if missing:
            raise VectorStoreError(
                f"{len(missing)} of {len(keys)} texts have no stored vector for vectorizer "
                f"version {version[:12]}; run python -m classifier.vectorize first"
            )
        dimension = found[keys[0]]["dimension"]
        rows, columns, values = [], [], []
        for position, key in enumerate(keys):
            record = found[key]
            rows.extend([position] * len(record["indices"]))
            columns.extend(record["indices"])
            values.extend(record["values"])
        return csr_matrix(
            (np.array(values, dtype=np.float64), (rows, columns)),
            shape=(len(keys), dimension),
        )

    def count(self, version: str) -> int:
        return self.collection.count_documents({"vectorizer_version": version})


def get_vector_store() -> VectorStore:
    import os

    import django
    from django.conf import settings

    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api6.settings")
        django.setup()
    from core.mongo import get_mongo_db

    return VectorStore(get_mongo_db()[COLLECTION_NAME])
