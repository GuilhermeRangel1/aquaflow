from dataclasses import dataclass
from datetime import UTC, datetime
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
    detector_type: Literal["continuous_flow"]
    score: Decimal
    severity: Literal["high"]
    reason: str
    window_start: datetime
    window_end: datetime
    evidence: dict[str, int | float]


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
