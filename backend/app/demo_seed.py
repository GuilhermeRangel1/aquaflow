"""Create synthetic local data so the AquaFlow MVP can be explored immediately."""

import asyncio
import secrets
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import hash_device_key, hash_password
from app.db.models import Alert, AnomalyEvent, Device, Property, TelemetryReading, User
from app.db.session import create_session_factory
from app.services.anomaly_detection import evaluate_continuous_flow

DEMO_EMAIL = "demo@example.com"
LEGACY_DEMO_EMAIL = "demo@aquaflow.local"
PROPERTY_TIMEZONE = "America/Sao_Paulo"


async def seed_demo_data(
    session_factory: async_sessionmaker[AsyncSession], *, password: str
) -> bool:
    """Add the local demo dataset without overwriting existing demo data."""
    async with session_factory() as session:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        user = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = await session.scalar(
                select(User).where(User.email == LEGACY_DEMO_EMAIL)
            )
            if user is not None:
                user.email = DEMO_EMAIL
        created = user is None
        if user is None:
            user = User(
                name="Conta de demonstração",
                email=DEMO_EMAIL,
                password_hash=hash_password(password),
                created_at=now,
            )
            session.add(user)
            await session.flush()

        property_row = await session.scalar(
            select(Property).where(
                Property.owner_id == user.id,
                Property.name == "Casa da demonstração",
            )
        )
        if property_row is None:
            property_row = Property(
                owner_id=user.id,
                name="Casa da demonstração",
                timezone=PROPERTY_TIMEZONE,
                volume_unit="L",
                continuous_flow_threshold_liters_minute=Decimal("0.1"),
                continuous_flow_duration_minutes=360,
                late_reading_window_days=7,
                created_at=now,
            )
            session.add(property_row)
            await session.flush()
            created = True

        device_specs = (
            ("AF-DEMO-001", "Medidor principal", now),
            ("AF-DEMO-002", "Irrigação externa", now),
            ("AF-DEMO-003", "Medidor de reserva", None),
            ("AF-DEMO-004", "Lavanderia", now),
        )
        devices: dict[str, Device] = {}
        for serial, name, last_seen in device_specs:
            device = await session.scalar(
                select(Device).where(Device.serial_number == serial)
            )
            if device is None:
                device = _device(
                    property_row.id, serial, name, now, last_seen_at=last_seen
                )
                session.add(device)
                created = True
            elif device.property_id != property_row.id:
                raise RuntimeError(
                    f"Dispositivo demonstrativo {serial} pertence a outra propriedade."
                )
            else:
                # Demo meters represent synthetic heartbeats, refreshed at seed time.
                device.last_seen_at = last_seen
            devices[serial] = device
        await session.flush()

        existing_event_ids = set(
            (await session.scalars(
                select(TelemetryReading.event_id).where(
                    TelemetryReading.device_id.in_([d.id for d in devices.values()])
                )
            )).all()
        )
        samples = (
            _daily_readings(devices["AF-DEMO-001"], now)
            + _continuous_flow_readings(devices["AF-DEMO-002"], now)
            + _laundry_readings(devices["AF-DEMO-004"], now)
        )
        missing = [sample for sample in samples if sample.event_id not in existing_event_ids]
        if missing:
            session.add_all(missing)
            await session.flush()
            created = True
            await evaluate_continuous_flow(
                session,
                device=devices["AF-DEMO-002"],
                property_row=property_row,
                through=now,
            )

        if await _add_sample_alerts(
            session,
            property_row,
            devices["AF-DEMO-004"],
            devices["AF-DEMO-003"],
            now,
        ):
            created = True
        await session.commit()
        return created


def _device(
    property_id: UUID,
    serial_number: str,
    name: str,
    created_at: datetime,
    *,
    last_seen_at: datetime | None = None,
) -> Device:
    return Device(
        property_id=property_id,
        serial_number=serial_number,
        name=name,
        device_key_hash=hash_device_key(secrets.token_urlsafe(32)),
        expected_interval_seconds=300,
        created_at=created_at,
        last_seen_at=last_seen_at,
    )


def _daily_readings(device: Device, now: datetime) -> list[TelemetryReading]:
    zone = ZoneInfo(PROPERTY_TIMEZONE)
    today = now.astimezone(zone).date()
    readings: list[TelemetryReading] = []
    total = Decimal("1200")
    for days_ago in range(6, -1, -1):
        day: date = today - timedelta(days=days_ago)
        sessions_for_day = (
            ("manha", 7, Decimal("18.4")),
            ("almoco", 12, Decimal("9.2")),
            ("pausa", 14, Decimal("6.7")),
            ("tarde", 16, Decimal("13.8")),
            ("noite", 19, Decimal("27.6")),
        )
        for session_name, hour, liters in sessions_for_day:
            local_start = datetime.combine(day, time(hour, 30), tzinfo=zone)
            start = local_start.astimezone(UTC)
            end = start + timedelta(minutes=5)
            if end >= now:
                continue
            first_volume = total
            total += liters
            for suffix, recorded_at, volume in (
                ("inicio", start, first_volume),
                ("fim", end, total),
            ):
                readings.append(
                    TelemetryReading(
                        device_id=device.id,
                        event_id=f"demo-{day:%Y%m%d}-{session_name}-{suffix}",
                        recorded_at=recorded_at,
                        received_at=now,
                        cumulative_volume_liters=volume,
                        quality="valid",
                    )
                )
    return readings


def _laundry_readings(device: Device, now: datetime) -> list[TelemetryReading]:
    """A second cumulative meter with regular, lower-volume daily use."""
    zone = ZoneInfo(PROPERTY_TIMEZONE)
    today = now.astimezone(zone).date()
    total = Decimal("320")
    readings: list[TelemetryReading] = []
    for days_ago in range(6, -1, -1):
        start = datetime.combine(
            today - timedelta(days=days_ago), time(10, 0), tzinfo=zone
        ).astimezone(UTC)
        end = start + timedelta(minutes=5)
        if end >= now:
            continue
        first = total
        total += Decimal("42.5") + Decimal(days_ago % 3 * 4)
        for suffix, recorded_at, volume in (("inicio", start, first), ("fim", end, total)):
            readings.append(TelemetryReading(
                device_id=device.id,
                event_id=f"demo-laundry-{today - timedelta(days=days_ago):%Y%m%d}-{suffix}",
                recorded_at=recorded_at,
                received_at=now,
                cumulative_volume_liters=volume,
                quality="valid",
            ))
    return readings


async def _add_sample_alerts(
    session: AsyncSession,
    property_row: Property,
    device: Device,
    offline_device: Device,
    now: datetime,
) -> bool:
    existing = list((await session.scalars(
        select(AnomalyEvent).where(AnomalyEvent.property_id == property_row.id)
    )).all())
    existing_keys = {
        event.evidence.get("demo_fixture_key")
        for event in existing
        if isinstance(event.evidence, dict)
    }
    sample_time = now - timedelta(days=2)
    zone = ZoneInfo(property_row.timezone)
    night_start = datetime.combine(
        sample_time.astimezone(zone).date() - timedelta(days=1), time(22), tzinfo=zone
    ).astimezone(UTC)
    night_end = night_start + timedelta(minutes=15)
    offline_last_seen = sample_time - timedelta(minutes=40)
    fixtures: tuple[
        tuple[str, str, str, str, Device, datetime, datetime, dict[str, str | int | float]], ...
    ] = (
        (
            "acknowledged",
            "night_consumption",
            "Consumo noturno acima do padrão",
            "demo-alert-night",
            device,
            night_start,
            night_end,
            {
                "baseline_daytime_median_liters_minute": 0.05,
                "minimum_increase_liters_minute": 0.1,
                "threshold_liters_minute": 0.15,
                "observed_flow_rate_liters_minute": 0.18,
                "required_duration_minutes": 15,
                "observed_duration_minutes": 15,
                "measured_interval_count": 3,
                "max_sample_gap_seconds": 300,
                "night_window": "22:00-06:00",
                "timezone": property_row.timezone,
                "baseline_interval_count": 24,
            },
        ),
        (
            "resolved",
            "demo_sample",
            "Pico de consumo já normalizado",
            "demo-alert-resolved",
            device,
            sample_time,
            sample_time + timedelta(hours=1),
            {},
        ),
        (
            "false_positive",
            "demo_sample",
            "Leitura compatível com uso planejado",
            "demo-alert-false-positive",
            device,
            sample_time,
            sample_time + timedelta(hours=1),
            {},
        ),
        (
            "open",
            "device_offline",
            "Medidor sem comunicação por mais de dois intervalos",
            "demo-alert-offline",
            offline_device,
            offline_last_seen + timedelta(seconds=600),
            sample_time,
            {
                "last_seen_at": offline_last_seen.isoformat(),
                "expected_interval_seconds": 300,
                "offline_threshold_seconds": 600,
                "seconds_since_last_seen": 2400,
            },
        ),
    )
    added = False
    for (
        status,
        detector_type,
        reason,
        fixture_key,
        sample_device,
        window_start,
        window_end,
        evidence,
    ) in fixtures:
        if fixture_key in existing_keys:
            continue
        anomaly = AnomalyEvent(
            property_id=property_row.id,
            device_id=sample_device.id,
            detector_type=detector_type,
            score=Decimal("0.650"),
            severity="medium",
            reason=f"Amostra demonstrativa: {reason}",
            window_start=window_start,
            window_end=window_end,
            evidence={
                **evidence,
                "is_demo_sample": True,
                "demo_fixture_key": fixture_key,
            },
            detected_at=window_end,
        )
        session.add(anomaly)
        await session.flush()
        acknowledged = anomaly.detected_at + timedelta(minutes=10) if status != "open" else None
        resolved = (
            anomaly.detected_at + timedelta(minutes=30)
            if status in {"resolved", "false_positive"}
            else None
        )
        session.add(Alert(
            anomaly_id=anomaly.id,
            status=status,
            channel="dashboard",
            created_at=anomaly.detected_at,
            acknowledged_at=acknowledged,
            resolved_at=resolved,
        ))
        added = True
    return added


def _continuous_flow_readings(device: Device, now: datetime) -> list[TelemetryReading]:
    start = now - timedelta(hours=6)
    return [
        TelemetryReading(
            device_id=device.id,
            event_id=f"demo-flow-{index:03d}",
            recorded_at=start + timedelta(minutes=5 * index),
            received_at=now,
            flow_rate_liters_minute=Decimal("0.2"),
            quality="valid",
        )
        for index in range(73)
    ]


async def main() -> None:
    if not settings.demo_mode:
        return
    factory = create_session_factory(settings)
    try:
        created = await seed_demo_data(factory, password=settings.demo_user_password)
        if created:
            print("Dados sintéticos de demonstração preparados.")
        else:
            print("Dados sintéticos já estão atualizados; nada foi alterado.")
    finally:
        bind = factory.kw.get("bind")
        if bind is not None:
            await bind.dispose()


if __name__ == "__main__":
    asyncio.run(main())
