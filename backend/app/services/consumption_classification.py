from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, AnomalyEvent, Device, MLInference, TelemetryReading
from app.domain.consumption import Sample, interval_volume


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def classify_consumption(
    session: AsyncSession, property_id: UUID, start: datetime, end: datetime
) -> dict[str, Decimal]:
    devices = list(
        (
            await session.scalars(
                select(Device).where(Device.property_id == property_id, Device.is_active.is_(True))
            )
        ).all()
    )
    totals = {"normal": Decimal(0), "flagged": Decimal(0), "unclassified": Decimal(0)}
    rules = (
        await session.execute(
            select(AnomalyEvent.device_id, AnomalyEvent.window_start, AnomalyEvent.window_end)
            .join(Alert, Alert.anomaly_id == AnomalyEvent.id)
            .where(
                AnomalyEvent.property_id == property_id,
                AnomalyEvent.detector_type.in_(("continuous_flow", "night_consumption")),
                AnomalyEvent.window_end > start,
                AnomalyEvent.window_start < end,
                Alert.status != "false_positive",
            )
        )
    ).all()
    rules_by_device: dict[UUID, list[tuple[datetime, datetime]]] = {}
    for rule in rules:
        rules_by_device.setdefault(rule.device_id, []).append(
            (_as_utc(rule.window_start), _as_utc(rule.window_end))
        )
    alert_reviews = (
        await session.execute(
            select(Alert.status, AnomalyEvent.evidence)
            .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
            .where(
                AnomalyEvent.property_id == property_id,
                AnomalyEvent.detector_type == "ml_anomaly",
                AnomalyEvent.evidence["episode_policy"].as_string() == "consecutive-v1",
                AnomalyEvent.window_end > start,
                AnomalyEvent.window_start < end,
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
        )
    ).all()
    review_by_inference: dict[str, str] = {}
    for status, evidence in alert_reviews:
        inference_ids = evidence.get("ml_inference_ids")
        if isinstance(inference_ids, list):
            for inference_id in inference_ids:
                if isinstance(inference_id, str):
                    review_by_inference.setdefault(inference_id, status)

    for device in devices:
        readings = (
            select(
                TelemetryReading.id,
                TelemetryReading.recorded_at,
                TelemetryReading.cumulative_volume_liters,
                TelemetryReading.flow_rate_liters_minute,
            )
            .where(
                TelemetryReading.device_id == device.id,
                TelemetryReading.quality == "valid",
                TelemetryReading.recorded_at
                >= start - timedelta(seconds=device.expected_interval_seconds * 2),
                TelemetryReading.recorded_at <= end + timedelta(minutes=10),
            )
            .order_by(TelemetryReading.recorded_at, TelemetryReading.id)
            .execution_options(yield_per=1000)
        )
        ranked = (
            select(
                MLInference.id,
                MLInference.reading_id,
                MLInference.predicted_anomaly,
                MLInference.feature_values["elapsed_minutes"].label("elapsed_minutes"),
                MLInference.explanation["input_derivation"].as_string().label("derivation"),
                TelemetryReading.recorded_at,
                func.row_number()
                .over(
                    partition_by=MLInference.reading_id,
                    order_by=(MLInference.inferred_at.desc(), MLInference.id.desc()),
                )
                .label("position"),
            )
            .join(TelemetryReading, TelemetryReading.id == MLInference.reading_id)
            .where(
                TelemetryReading.device_id == device.id,
                TelemetryReading.recorded_at > start,
                TelemetryReading.recorded_at <= end + timedelta(minutes=10),
            )
            .subquery()
        )
        results = await session.stream(select(ranked).where(ranked.c.position == 1))
        direct_predictions: dict[UUID, bool | None] = {}
        windows: list[tuple[datetime, datetime, bool | None]] = []
        try:
            async for inference in results:
                prediction = inference.predicted_anomaly
                if prediction is True and review_by_inference.get(str(inference.id)) not in (
                    "open",
                    "acknowledged",
                    "resolved",
                ):
                    prediction = None
                if inference.derivation != "cumulative_volume_5min_window":
                    direct_predictions[inference.reading_id] = prediction
                    continue
                minutes = inference.elapsed_minutes
                if (
                    inference.predicted_anomaly is not None
                    and isinstance(minutes, (int, float))
                    and 0 < minutes <= 10
                ):
                    window_end = _as_utc(inference.recorded_at)
                    windows.append(
                        (
                            window_end - timedelta(minutes=minutes),
                            window_end,
                            prediction,
                        )
                    )
        finally:
            await results.close()
        windows.sort(key=lambda window: window[1])
        window_index = 0
        rule_windows = iter(sorted(rules_by_device.get(device.id, [])))
        next_rule = next(rule_windows, None)
        rule_end = start
        rows = await session.stream(readings)
        try:
            previous = await rows.fetchone()
            if previous is None:
                continue
            async for current in rows:
                previous, prior = current, previous
                previous_at = _as_utc(prior.recorded_at)
                current_at = _as_utc(current.recorded_at)
                overlap_start = max(previous_at, start)
                overlap_end = min(current_at, end)
                if overlap_end <= overlap_start:
                    continue
                volume = interval_volume(
                    Sample(
                        previous_at, prior.cumulative_volume_liters, prior.flow_rate_liters_minute
                    ),
                    Sample(
                        current_at,
                        current.cumulative_volume_liters,
                        current.flow_rate_liters_minute,
                    ),
                    device.expected_interval_seconds,
                )
                if volume is None:
                    continue
                while window_index < len(windows) and windows[window_index][1] < overlap_end:
                    window_index += 1
                prediction = None
                if current.id in direct_predictions:
                    prediction = direct_predictions[current.id]
                elif window_index < len(windows):
                    window_start, window_end, predicted = windows[window_index]
                    if window_start <= overlap_start and overlap_end <= window_end:
                        prediction = predicted
                while next_rule is not None and next_rule[0] <= overlap_start:
                    rule_end = max(rule_end, next_rule[1])
                    next_rule = next(rule_windows, None)
                flagged_by_rule = overlap_end <= rule_end
                category = (
                    "flagged"
                    if flagged_by_rule or prediction is True
                    else "normal"
                    if prediction is False
                    else "unclassified"
                )
                totals[category] += (
                    volume
                    * Decimal(str((overlap_end - overlap_start).total_seconds()))
                    / Decimal(str((current_at - previous_at).total_seconds()))
                )
        finally:
            await rows.close()
    return totals
