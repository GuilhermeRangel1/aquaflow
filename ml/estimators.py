"""Classifiers whose regularization adapts to the available training data."""

import math

from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.neighbors import KNeighborsClassifier
from sklearn.utils.validation import check_is_fitted


class ProportionalKNeighborsClassifier(ClassifierMixin, BaseEstimator):
    """Keep the neighborhood fraction consistent across temporal folds and refits."""

    def __init__(self, neighbor_fraction: float = 0.025):
        self.neighbor_fraction = neighbor_fraction

    def fit(self, values, targets):
        if not 0 < self.neighbor_fraction <= 1:
            raise ValueError("neighbor_fraction must be in (0, 1]")
        self.n_neighbors_ = min(
            len(values), max(3, math.ceil(len(values) * self.neighbor_fraction))
        )
        self.estimator_ = KNeighborsClassifier(
            n_neighbors=self.n_neighbors_, weights="uniform"
        ).fit(values, targets)
        self.classes_ = self.estimator_.classes_
        self.n_features_in_ = self.estimator_.n_features_in_
        return self

    def predict(self, values):
        check_is_fitted(self, "estimator_")
        return self.estimator_.predict(values)

    def predict_proba(self, values):
        check_is_fitted(self, "estimator_")
        return self.estimator_.predict_proba(values)
