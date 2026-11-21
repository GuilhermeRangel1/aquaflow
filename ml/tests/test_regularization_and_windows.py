"""Unit tests for adaptive KNN, simplest-within-one-SE selection and 5-minute windows."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

ML = Path(__file__).resolve().parents[1]
if str(ML) not in sys.path:
    sys.path.insert(0, str(ML))

from estimators import ProportionalKNeighborsClassifier
from inference_worker import _aggregate_window
from train_model import _regularized_trial

BOUNDARY = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def test_knn_neighbors_scale_with_training_size_and_have_a_floor() -> None:
    rng = np.random.default_rng(0)
    for size, expected in ((1000, 25), (40, 3)):
        values = rng.normal(size=(size, 3))
        targets = np.arange(size) % 2
        model = ProportionalKNeighborsClassifier(neighbor_fraction=0.025).fit(values, targets)
        assert model.n_neighbors_ == expected
        assert model.predict_proba(values[:2]).shape == (2, 2)


def test_regularized_trial_prefers_simplest_within_one_standard_error() -> None:
    def trial(depth: int, scores: list[float]) -> dict:
        return {
            "parameters": {"model__max_depth": depth, "model__min_samples_leaf": 20},
            "validation_scores": scores,
            "train_scores": scores,
        }

    complex_best = trial(3, [0.80, 0.84, 0.82])
    simple_close = trial(2, [0.81, 0.82, 0.815])
    simple_bad = trial(1, [0.50, 0.50, 0.50])

    chosen = _regularized_trial([complex_best, simple_close, simple_bad])

    assert chosen["parameters"]["model__max_depth"] == 2


class _FakeConnection:
    def __init__(self, history: list[dict]) -> None:
        self.history = history

    async def fetch(self, *_args: object) -> list[dict]:
        return self.history


def _sample(offset_seconds: int, volume: str | None, quality: str = "valid") -> dict:
    return {
        "recorded_at": BOUNDARY + timedelta(seconds=offset_seconds),
        "cumulative_volume_liters": None if volume is None else Decimal(volume),
        "quality": quality,
    }


def _window(history: list[dict], last: dict) -> tuple[dict | None, str | None]:
    reading = {
        **last,
        "device_id": "device",
        "expected_interval_seconds": 30,
        "window_start": BOUNDARY,
        "timezone": "America/Sao_Paulo",
    }
    return asyncio.run(_aggregate_window(_FakeConnection(history), reading))


def _full_history() -> list[dict]:
    # 10 samples every 30 s inside the bucket, preceded by one just before it.
    return [_sample(-20, "100"), *[_sample(30 * i, str(100 + i)) for i in range(10)]]


def test_complete_window_yields_features() -> None:
    history = _full_history()
    features, reason = _window(history, _sample(299, "111"))
    assert reason is None and features is not None


def test_window_is_skipped_without_coverage_gap_or_with_decreasing_volume() -> None:
    assert _window([], _sample(299, "111"))[0] is None
    gap = [_sample(-20, "100"), _sample(30, "101")]
    assert _window(gap, _sample(299, "111"))[0] is None
    decreasing = [*_full_history(), ]
    decreasing[5] = _sample(120, "50")
    assert _window(decreasing, _sample(299, "111"))[0] is None
    invalid = _full_history()
    invalid[3] = _sample(60, "102", quality="invalid")
    assert _window(invalid, _sample(299, "111"))[0] is None
