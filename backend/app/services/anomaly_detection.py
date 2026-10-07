from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, AnomalyEvent, Device, Property, TelemetryReading
from app.domain.anomalies import ReadingSample, detect_continuous_flow


async def evaluate_continuous_flow(
    session: AsyncSession,
    *,
    device: Device,
    property_row: Property,
    through: datetime,
) -> None:
    through_utc = _as_utc(through)
    lookback = timedelta(minutes=property_row.continuous_flow_duration_minutes) + timedelta(
        seconds=device.expected_interval_seconds * 2
    )
    readings = list(
        (
            await session.scalars(
                select(TelemetryReading)
                .where(
                    TelemetryReading.device_id == device.id,
                    TelemetryReading.recorded_at >= through_utc - lookback,
                    TelemetryReading.recorded_at <= through_utc,
                )
                .order_by(TelemetryReading.recorded_at)
            )
        ).all()
    )
    candidate = detect_continuous_flow(
        [
            ReadingSample(
                recorded_at=reading.recorded_at,
                quality=reading.quality,
                cumulative_volume_liters=reading.cumulative_volume_liters,
                flow_rate_liters_minute=reading.flow_rate_liters_minute,
            )
            for reading in readings
        ],
        expected_interval_seconds=device.expected_interval_seconds,
        minimum_flow_rate_liters_minute=Decimal(
            property_row.continuous_flow_threshold_liters_minute
        ),
        required_duration_minutes=property_row.continuous_flow_duration_minutes,
    )
    if candidate is None:
        return

    active = await session.execute(
        select(Alert, AnomalyEvent)
        .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
        .where(
            AnomalyEvent.device_id == device.id,
            AnomalyEvent.detector_type == candidate.detector_type,
            Alert.status.in_(["open", "acknowledged"]),
        )
        .order_by(Alert.created_at.desc())
        .limit(1)
    )
    active_pair = active.first()
    now = datetime.now(UTC)
    if active_pair is not None:
        _, anomaly = active_pair
        occurrence_count = int(anomaly.evidence.get("occurrence_count", 1)) + 1
        anomaly.window_end = candidate.window_end
        anomaly.evidence = {
            **anomaly.evidence,
            **candidate.evidence,
            "occurrence_count": occurrence_count,
            "last_detected_at": now.isoformat(),
        }
        return

    anomaly = AnomalyEvent(
        property_id=property_row.id,
        device_id=device.id,
        detector_type=candidate.detector_type,
        score=candidate.score,
        severity=candidate.severity,
        reason=candidate.reason,
        window_start=candidate.window_start,
        window_end=candidate.window_end,
        evidence={**candidate.evidence, "occurrence_count": 1},
        detected_at=now,
    )
    session.add(anomaly)
    await session.flush()
    session.add(
        Alert(
            anomaly_id=anomaly.id,
            status="open",
            channel="dashboard",
            created_at=now,
        )
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
