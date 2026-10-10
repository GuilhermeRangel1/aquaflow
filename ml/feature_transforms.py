"""Shared deterministic feature transformations for training and inference."""

import math
from datetime import datetime
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
