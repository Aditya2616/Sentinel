"""TF-IDF + logistic regression baseline (word and character n-grams)."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


class TfidfBaseline:
    def __init__(self) -> None:
        self.word = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=200_000)
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True, max_features=300_000)
        self.clf = LogisticRegression(C=8.0, max_iter=2000, solver="liblinear")

    def _x(self, texts: list[str], fit: bool = False):
        if fit:
            return hstack([self.word.fit_transform(texts), self.char.fit_transform(texts)]).tocsr()
        return hstack([self.word.transform(texts), self.char.transform(texts)]).tocsr()

    def fit(self, texts: list[str], y: list[int]) -> TfidfBaseline:
        self.clf.fit(self._x(texts, fit=True), np.asarray(y))
        return self

    def score(self, texts: list[str]) -> np.ndarray:
        return self.clf.predict_proba(self._x(texts))[:, 1]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> TfidfBaseline:
        return joblib.load(path)
