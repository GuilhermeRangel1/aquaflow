from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Literal
from zoneinfo import ZoneInfo

Granularity = Literal["hour", "day", "month"]


@dataclass(frozen=True, slots=True)
class Sample:
    recorded_at: datetime
    cumulative_volume_liters: Decimal | None
    flow_rate_liters_minute: Decimal | None


@dataclass(frozen=True, slots=True)
class ConsumptionBucket:
    bucket_start: datetime
    volume_liters: Decimal
    sample_count: int


def interval_volume(
    previous: Sample,
    current: Sample,
    expected_interval_seconds: int,
) -> Decimal | None:
    """Calculate volume only across adjacent, sufficiently close compatible samples."""
    previous_at = as_utc(previous.recorded_at)
    current_at = as_utc(current.recorded_at)
    duration_seconds = Decimal(str((current_at - previous_at).total_seconds()))
    if duration_seconds <= 0 or duration_seconds > Decimal(expected_interval_seconds * 2):
        return None

    if (
        previous.cumulative_volume_liters is not None
        and current.cumulative_volume_liters is not None
    ):
        delta = current.cumulative_volume_liters - previous.cumulative_volume_liters
        return delta if delta >= 0 else None

    if previous.flow_rate_liters_minute is not None and current.flow_rate_liters_minute is not None:
        average_rate = (
            previous.flow_rate_liters_minute + current.flow_rate_liters_minute
        ) / Decimal(2)
        return average_rate * duration_seconds / Decimal(60)

    return None


def aggregate_samples(
    samples: list[Sample],
    expected_interval_seconds: int,
    timezone_name: str,
    granularity: Granularity,
    *,
    start: datetime,
    end: datetime,
) -> list[ConsumptionBucket]:
    zone = ZoneInfo(timezone_name)
    ordered = sorted(samples, key=lambda sample: as_utc(sample.recorded_at))
    totals: dict[datetime, tuple[Decimal, int]] = {}

    for previous, current in pairwise(ordered):
        volume = interval_volume(previous, current, expected_interval_seconds)
        if volume is None:
            continue
        _distribute_interval(
            totals,
            as_utc(previous.recorded_at),
            as_utc(current.recorded_at),
            volume,
            zone,
            granularity,
            as_utc(start),
            as_utc(end),
        )

    return [
        ConsumptionBucket(bucket_start=key, volume_liters=value[0], sample_count=value[1])
        for key, value in sorted(totals.items())
    ]


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


def _bucket_start(value: datetime, zone: ZoneInfo, granularity: Granularity) -> datetime:
    local = value.astimezone(zone)
    if granularity == "hour":
        local_start = local.replace(minute=0, second=0, microsecond=0)
    elif granularity == "day":
        local_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        local_start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(UTC)


def _next_bucket_start(
    current_bucket_start: datetime,
    zone: ZoneInfo,
    granularity: Granularity,
) -> datetime:
    local_start = current_bucket_start.astimezone(zone)
    if granularity == "hour":
        return current_bucket_start + timedelta(hours=1)
    if granularity == "day":
        next_local_date = local_start.date() + timedelta(days=1)
        return datetime.combine(next_local_date, datetime.min.time(), tzinfo=zone).astimezone(UTC)
    if local_start.month == 12:
        next_year, next_month = local_start.year + 1, 1
    else:
        next_year, next_month = local_start.year, local_start.month + 1
    return datetime(next_year, next_month, 1, tzinfo=zone).astimezone(UTC)


def _distribute_interval(
    totals: dict[datetime, tuple[Decimal, int]],
    interval_start: datetime,
    interval_end: datetime,
    volume: Decimal,
    zone: ZoneInfo,
    granularity: Granularity,
    range_start: datetime,
    range_end: datetime,
) -> None:
    full_duration = Decimal(str((interval_end - interval_start).total_seconds()))
    cursor = interval_start
    while cursor < interval_end:
        bucket = _bucket_start(cursor, zone, granularity)
        boundary = _next_bucket_start(bucket, zone, granularity)
        segment_end = min(interval_end, boundary)
        overlap_start = max(cursor, range_start)
        overlap_end = min(segment_end, range_end)
        if overlap_end > overlap_start:
            segment_seconds = Decimal(str((overlap_end - overlap_start).total_seconds()))
            contribution = volume * segment_seconds / full_duration
            old_volume, old_count = totals.get(bucket, (Decimal(0), 0))
            totals[bucket] = (old_volume + contribution, old_count + 1)
        cursor = segment_end
