"""Shared deterministic feature transformations for training and inference."""

import hashlib
import math
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

FEATURE_NAMES = (
    "flow_rate_liters_minute",
    "volume_delta_liters",
    "elapsed_minutes",
    "local_hour_sin",
    "local_hour_cos",
    "local_weekday_sin",
    "local_weekday_cos",
)


def transform_reading(
    *,
    flow_rate_liters_minute: float,
    volume_delta_liters: float,
    elapsed_minutes: float,
    recorded_at: datetime,
    timezone: str,
) -> dict[str, float]:
    """Build model features from one reading and its preceding reading."""
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("recorded_at must include a timezone")
    local_timestamp = recorded_at.astimezone(ZoneInfo(timezone))
    hour = local_timestamp.hour + local_timestamp.minute / 60
    weekday = local_timestamp.weekday()
    return {
        "flow_rate_liters_minute": float(flow_rate_liters_minute),
        "volume_delta_liters": round(float(volume_delta_liters), 6),
        "elapsed_minutes": round(float(elapsed_minutes), 6),
        "local_hour_sin": round(math.sin(2 * math.pi * hour / 24), 8),
        "local_hour_cos": round(math.cos(2 * math.pi * hour / 24), 8),
        "local_weekday_sin": round(math.sin(2 * math.pi * weekday / 7), 8),
        "local_weekday_cos": round(math.cos(2 * math.pi * weekday / 7), 8),
    }


def transform_window(
    history: list[Any], reading: Any, window_seconds: int
) -> tuple[dict[str, float] | None, str | None]:
    """Build features from a complete interval and its preceding baseline."""
    end = reading["recorded_at"]
    tolerance = timedelta(seconds=reading["expected_interval_seconds"] * 1.5)
    window = timedelta(seconds=window_seconds)
    boundary = reading["window_start"]
    coverage_tolerance = min(tolerance, timedelta(seconds=60))
    candidates = [
        i for i, sample in enumerate(history)
        if sample["recorded_at"] < boundary
    ]
    if not candidates or end - boundary < window - coverage_tolerance:
        return None, "Cobertura insuficiente para a janela de cinco minutos."
    # Reuse the previous bucket's last sample as the next volume baseline.
    samples = [*history[candidates[-1]:], reading]
    for before, after in pairwise(samples):
        step = after["recorded_at"] - before["recorded_at"]
        if not timedelta(0) < step <= tolerance:
            return None, "Lacuna ou timestamp duplicado na janela de cinco minutos."
    if any(
        sample["quality"] != "valid" or sample["cumulative_volume_liters"] is None
        for sample in samples
    ):
        return None, "Volume acumulado válido insuficiente na janela de cinco minutos."
    volumes = [sample["cumulative_volume_liters"] for sample in samples]
    if any(after < before for before, after in pairwise(volumes)):
        return None, "O contador de volume diminuiu dentro da janela de cinco minutos."
    elapsed = (end - samples[0]["recorded_at"]).total_seconds() / 60
    delta = float(volumes[-1] - volumes[0])
    return transform_reading(
        flow_rate_liters_minute=delta / elapsed,
        volume_delta_liters=delta,
        elapsed_minutes=elapsed,
        recorded_at=boundary + window,
        timezone=reading["timezone"],
    ), None


def inference_version(model_hash: str, threshold: float) -> str:
    """Preserve the identity already stored for the original 0.5 policy."""
    if threshold == 0.5:
        return model_hash
    return hashlib.sha256(f"{model_hash}:threshold:{threshold.hex()}".encode("ascii")).hexdigest()
