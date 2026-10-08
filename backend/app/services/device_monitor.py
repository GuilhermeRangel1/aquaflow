import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, AnomalyEvent, Device, Property

logger = logging.getLogger(__name__)
OFFLINE_DETECTOR = "device_offline"
OFFLINE_POLL_SECONDS = 60


async def scan_offline_devices(session: AsyncSession, *, now: datetime | None = None) -> None:
    """Create one grouped dashboard alert after a device misses two intervals."""
    current = now or datetime.now(UTC)
    rows = list(
        (
            await session.execute(
                select(Device, Property)
                .join(Property, Property.id == Device.property_id)
                .where(Device.last_seen_at.is_not(None), Device.is_active.is_(True))
            )
        ).all()
    )
    for device, property_row in rows:
        last_seen = _as_utc(device.last_seen_at)
        threshold = timedelta(seconds=device.expected_interval_seconds * 2)
        if current - last_seen <= threshold:
            continue

        active = await session.execute(
            select(Alert, AnomalyEvent)
            .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
            .where(
                AnomalyEvent.device_id == device.id,
                AnomalyEvent.detector_type == OFFLINE_DETECTOR,
                Alert.status.in_(["open", "acknowledged"]),
            )
            .order_by(Alert.created_at.desc())
            .limit(1)
        )
        if active.first() is not None:
            continue

        anomaly = AnomalyEvent(
            property_id=property_row.id,
            device_id=device.id,
            detector_type=OFFLINE_DETECTOR,
            score=0.8,
            severity="medium",
            reason=(
                "O medidor não envia leituras há mais de dois intervalos esperados. "
                "Verifique a alimentação e a conexão de rede do dispositivo."
            ),
            window_start=last_seen + threshold,
            window_end=current,
            evidence={
                "last_seen_at": last_seen.isoformat(),
                "expected_interval_seconds": device.expected_interval_seconds,
                "offline_threshold_seconds": device.expected_interval_seconds * 2,
                "seconds_since_last_seen": max(0, int((current - last_seen).total_seconds())),
            },
            detected_at=current,
        )
        session.add(anomaly)
        await session.flush()
        session.add(
            Alert(anomaly_id=anomaly.id, status="open", channel="dashboard", created_at=current)
        )


async def resolve_offline_alerts(session: AsyncSession, device: Device, *, now: datetime) -> None:
    active = list(
        (
            await session.execute(
                select(Alert, AnomalyEvent)
                .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
                .where(
                    AnomalyEvent.device_id == device.id,
                    AnomalyEvent.detector_type == OFFLINE_DETECTOR,
                    Alert.status.in_(["open", "acknowledged"]),
                )
            )
        ).all()
    )
    for alert, anomaly in active:
        alert.status = "resolved"
        alert.resolved_at = now
        anomaly.window_end = now
        anomaly.evidence = {**anomaly.evidence, "reconnected_at": now.isoformat()}


async def run_offline_monitor(
    session_factory: Callable[[], AsyncSession],
) -> None:
    while True:
        try:
            async with session_factory() as session, session.begin():
                await scan_offline_devices(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Offline device scan failed")
        await asyncio.sleep(OFFLINE_POLL_SECONDS)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("device last_seen_at is required")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
