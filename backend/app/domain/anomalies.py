from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class ReadingSample:
    recorded_at: datetime
    quality: str
    cumulative_volume_liters: Decimal | None
    flow_rate_liters_minute: Decimal | None


@dataclass(frozen=True)
class AnomalyCandidate:
    detector_type: Literal["continuous_flow", "night_consumption"]
    score: Decimal
    severity: Literal["high", "medium"]
    reason: str
    window_start: datetime
    window_end: datetime
    evidence: dict[str, int | float | str]


def detect_night_consumption(
    samples: list[ReadingSample],
    *,
    expected_interval_seconds: int,
    timezone_name: str,
    minimum_increase_liters_minute: Decimal = Decimal("0.1"),
    required_duration_minutes: int = 15,
) -> AnomalyCandidate | None:
    """Compare sustained 22:00–06:00 flow with this meter's recent daytime median."""
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(timezone_name)
    ordered = sorted(samples, key=lambda sample: _as_utc(sample.recorded_at))
    if not ordered:
        return None
    through = _as_utc(ordered[-1].recorded_at)
    through_local = through.astimezone(zone)
    if through_local.hour < 6:
        night_start_local = (through_local - timedelta(days=1)).replace(
            hour=22, minute=0, second=0, microsecond=0
        )
    elif through_local.hour >= 22:
        night_start_local = through_local.replace(hour=22, minute=0, second=0, microsecond=0)
    else:
        return None
    night_start = night_start_local.astimezone(UTC)
    cutoff = through - timedelta(days=7)
    daytime_rates: list[Decimal] = []
    intervals: list[tuple[datetime, datetime, int, Decimal]] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        start, end = _as_utc(previous.recorded_at), _as_utc(current.recorded_at)
        gap = int((end - start).total_seconds())
        if (
            previous.quality != "valid"
            or current.quality != "valid"
            or gap <= 0
            or gap > expected_interval_seconds * 2
        ):
            continue
        rate = _interval_rate(previous, current, gap, Decimal("-1"))
        if rate is None:
            continue
        midpoint = start + (end - start) / 2
        local = midpoint.astimezone(zone)
        is_night = local.hour >= 22 or local.hour < 6
        if start >= cutoff and not is_night:
            daytime_rates.append(rate)
        intervals.append((start, end, gap, rate))

    if len(daytime_rates) < 6:
        return None
    baseline = sorted(daytime_rates)[(len(daytime_rates) - 1) // 2]
    threshold = baseline + minimum_increase_liters_minute
    run_start: datetime | None = None
    run_end: datetime | None = None
    rates: list[tuple[Decimal, int]] = []
    gaps: list[int] = []
    for start, end, gap, rate in intervals:
        midpoint = start + (end - start) / 2
        local = midpoint.astimezone(zone)
        is_night = local.hour >= 22 or local.hour < 6
        if (
            start < night_start
            or not is_night
            or rate < threshold
            or (run_end is not None and start != run_end)
        ):
            run_start, run_end, rates, gaps = None, None, [], []
            continue
        if run_start is None:
            run_start = start
        run_end = end
        rates.append((rate, gap))
        gaps.append(gap)
        elapsed_minutes = int((run_end - run_start).total_seconds() // 60)
        if elapsed_minutes >= required_duration_minutes:
            observed = sum((value * seconds for value, seconds in rates), Decimal(0)) / sum(
                seconds for _, seconds in rates
            )
            return AnomalyCandidate(
                detector_type="night_consumption",
                score=Decimal("0.700"),
                severity="medium",
                reason=(
                    "O fluxo noturno ficou pelo menos 0,1 L/min acima da mediana diurna "
                    "recente por 15 minutos. Verifique os pontos de uso conectados ao medidor."
                ),
                window_start=run_start,
                window_end=run_end,
                evidence={
                    "baseline_daytime_median_liters_minute": float(baseline),
                    "minimum_increase_liters_minute": float(minimum_increase_liters_minute),
                    "threshold_liters_minute": float(threshold),
                    "observed_flow_rate_liters_minute": round(float(observed), 6),
                    "required_duration_minutes": required_duration_minutes,
                    "observed_duration_minutes": elapsed_minutes,
                    "measured_interval_count": len(rates),
                    "max_sample_gap_seconds": max(gaps),
                    "night_window": "22:00-06:00",
                    "timezone": timezone_name,
                    "baseline_interval_count": len(daytime_rates),
                },
            )
    return None


def detect_continuous_flow(
    samples: list[ReadingSample],
    *,
    expected_interval_seconds: int,
    minimum_flow_rate_liters_minute: Decimal,
    required_duration_minutes: int,
) -> AnomalyCandidate | None:
    ordered = sorted(samples, key=lambda sample: _as_utc(sample.recorded_at))
    run_start: datetime | None = None
    run_end: datetime | None = None
    run_rates: list[tuple[Decimal, int]] = []
    run_gaps: list[int] = []

    for previous, current in zip(ordered, ordered[1:], strict=False):
        previous_at = _as_utc(previous.recorded_at)
        current_at = _as_utc(current.recorded_at)
        gap_seconds = int((current_at - previous_at).total_seconds())
        if (
            previous.quality != "valid"
            or current.quality != "valid"
            or gap_seconds <= 0
            or gap_seconds > expected_interval_seconds * 2
        ):
            run_start = None
            run_end = None
            run_rates = []
            run_gaps = []
            continue

        interval_rate = _interval_rate(
            previous, current, gap_seconds, minimum_flow_rate_liters_minute
        )
        if interval_rate is None:
            run_start = None
            run_end = None
            run_rates = []
            run_gaps = []
            continue

        if run_start is None:
            run_start = previous_at
        run_end = current_at
        run_rates.append((interval_rate, gap_seconds))
        run_gaps.append(gap_seconds)

        elapsed_minutes = int((run_end - run_start).total_seconds() // 60)
        if elapsed_minutes >= required_duration_minutes:
            observed_rate = sum(
                (rate * Decimal(gap) for rate, gap in run_rates), Decimal(0)
            ) / sum(gap for _, gap in run_rates)
            return AnomalyCandidate(
                detector_type="continuous_flow",
                score=Decimal("0.900"),
                severity="high",
                reason=(
                    "A vazão permaneceu acima do limite configurado durante "
                    "uma janela sustentada. Verifique torneiras, descargas e "
                    "equipamentos conectados ao medidor."
                ),
                window_start=run_start,
                window_end=run_end,
                evidence={
                    "minimum_flow_rate_liters_minute": float(minimum_flow_rate_liters_minute),
                    "required_duration_minutes": required_duration_minutes,
                    "observed_flow_rate_liters_minute": round(float(observed_rate), 6),
                    "observed_duration_minutes": elapsed_minutes,
                    "measured_interval_count": len(run_rates),
                    "max_sample_gap_seconds": max(run_gaps),
                },
            )
    return None


def _interval_rate(
    previous: ReadingSample,
    current: ReadingSample,
    gap_seconds: int,
    minimum_flow_rate_liters_minute: Decimal,
) -> Decimal | None:
    if (
        previous.flow_rate_liters_minute is not None
        and current.flow_rate_liters_minute is not None
    ):
        if (
            previous.flow_rate_liters_minute <= minimum_flow_rate_liters_minute
            or current.flow_rate_liters_minute <= minimum_flow_rate_liters_minute
        ):
            return None
        return (previous.flow_rate_liters_minute + current.flow_rate_liters_minute) / 2

    if (
        previous.cumulative_volume_liters is not None
        and current.cumulative_volume_liters is not None
    ):
        delta = current.cumulative_volume_liters - previous.cumulative_volume_liters
        if delta < 0:
            return None
        interval_rate = delta / (Decimal(gap_seconds) / Decimal(60))
        if interval_rate <= minimum_flow_rate_liters_minute:
            return None
        return interval_rate
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
