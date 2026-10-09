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
            user = await session.scalar(select(User).where(User.email == LEGACY_DEMO_EMAIL))
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

        stale_last_seen = now - timedelta(days=2, minutes=40)
        device_specs = (
            ("AF-DEMO-001", "Medidor principal", now),
            ("AF-DEMO-002", "Irrigação externa", now),
            ("AF-DEMO-003", "Medidor de reserva", stale_last_seen),
            ("AF-DEMO-004", "Lavanderia", now),
        )
        devices: dict[str, Device] = {}
        for serial, name, last_seen in device_specs:
            device = await session.scalar(select(Device).where(Device.serial_number == serial))
            if device is None:
                device = _device(property_row.id, serial, name, now, last_seen_at=last_seen)
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
            (
                await session.scalars(
                    select(TelemetryReading.event_id).where(
                        TelemetryReading.device_id.in_([d.id for d in devices.values()])
                    )
                )
            ).all()
        )
        samples = (
            _daily_readings(devices["AF-DEMO-001"], now)
            + _continuous_flow_readings(devices["AF-DEMO-002"], now)
            + _irrigation_readings(devices["AF-DEMO-002"], now)
            + _laundry_readings(devices["AF-DEMO-004"], now)
            + _health_readings(devices, now)
            + [_offline_reading(devices["AF-DEMO-003"], stale_last_seen, now)]
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
    for days_ago in range(89, -1, -1):
        day: date = today - timedelta(days=days_ago)
        if days_ago > 6:
            # Backfill a three-month household baseline with variable, plausible
            # usage. Flow-rate samples avoid inventing a cumulative counter before
            # the older seven-day fixture already present in local databases.
            historical_sessions = (
                ("manha", 7, Decimal("18.4")),
                ("almoco", 12, Decimal("9.2")),
                ("pausa", 14, Decimal("6.7")),
                ("tarde", 16, Decimal("13.8")),
                ("noite", 19, Decimal("27.6")),
            )
            for session_index, (session_name, hour, baseline_liters) in enumerate(
                historical_sessions
            ):
                weekend_factor = Decimal("1.10") if day.weekday() >= 5 else Decimal("1.00")
                variation = Decimal(85 + ((day.toordinal() * 7 + session_index * 13) % 31)) / 100
                liters = baseline_liters * weekend_factor * variation
                average_rate = (liters / Decimal(5)).quantize(Decimal("0.001"))
                local_start = datetime.combine(day, time(hour, 30), tzinfo=zone)
                start = local_start.astimezone(UTC)
                end = start + timedelta(minutes=5)
                if end >= now:
                    continue
                battery = max(55, 96 - (90 - days_ago) // 8)
                signal = -48 - ((day.toordinal() + session_index * 5) % 19)
                for suffix, recorded_at, rate in (
                    ("inicio", start, average_rate * Decimal("0.85")),
                    ("fim", end, average_rate * Decimal("1.15")),
                ):
                    readings.append(
                        TelemetryReading(
                            device_id=device.id,
                            event_id=f"demo-history-{day:%Y%m%d}-{session_name}-{suffix}",
                            recorded_at=recorded_at,
                            received_at=now,
                            flow_rate_liters_minute=rate.quantize(Decimal("0.001")),
                            quality="valid",
                            battery_percent=battery,
                            signal_dbm=signal,
                            firmware_version="0.4.2-demo",
                        )
                    )
            continue
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
    for days_ago in range(89, -1, -1):
        day = today - timedelta(days=days_ago)
        if days_ago > 6:
            # A household washing machine usually runs a few loads per week,
            # rather than drawing water every day.
            if day.weekday() not in {1, 4, 6}:
                continue
            liters = Decimal(38 + ((day.toordinal() * 11) % 19))
            average_rate = (liters / Decimal(5)).quantize(Decimal("0.001"))
            start = datetime.combine(day, time(10, 0), tzinfo=zone).astimezone(UTC)
            end = start + timedelta(minutes=5)
            if end >= now:
                continue
            for suffix, recorded_at, rate in (
                ("inicio", start, average_rate * Decimal("0.85")),
                ("fim", end, average_rate * Decimal("1.15")),
            ):
                readings.append(
                    TelemetryReading(
                        device_id=device.id,
                        event_id=f"demo-laundry-history-{day:%Y%m%d}-{suffix}",
                        recorded_at=recorded_at,
                        received_at=now,
                        flow_rate_liters_minute=rate.quantize(Decimal("0.001")),
                        quality="valid",
                        battery_percent=max(55, 94 - (90 - days_ago) // 8),
                        signal_dbm=-50 - (day.toordinal() % 16),
                        firmware_version="0.4.2-demo",
                    )
                )
            continue
        start = datetime.combine(day, time(10, 0), tzinfo=zone).astimezone(UTC)
        end = start + timedelta(minutes=5)
        if end >= now:
            continue
        first = total
        total += Decimal("42.5") + Decimal(days_ago % 3 * 4)
        for suffix, recorded_at, volume in (("inicio", start, first), ("fim", end, total)):
            readings.append(
                TelemetryReading(
                    device_id=device.id,
                    event_id=f"demo-laundry-{today - timedelta(days=days_ago):%Y%m%d}-{suffix}",
                    recorded_at=recorded_at,
                    received_at=now,
                    cumulative_volume_liters=volume,
                    quality="valid",
                )
            )
    return readings


def _irrigation_readings(device: Device, now: datetime) -> list[TelemetryReading]:
    """Model short scheduled watering sessions alongside the recent anomaly."""
    zone = ZoneInfo(PROPERTY_TIMEZONE)
    today = now.astimezone(zone).date()
    readings: list[TelemetryReading] = []
    for days_ago in range(89, -1, -1):
        day = today - timedelta(days=days_ago)
        if day.weekday() not in {0, 3, 6}:
            continue
        start = datetime.combine(day, time(6, 0), tzinfo=zone).astimezone(UTC)
        variation = Decimal(90 + (day.toordinal() % 21)) / 100
        rate = (Decimal("0.6") * variation).quantize(Decimal("0.001"))
        for sample_index in range(7):
            recorded_at = start + timedelta(minutes=5 * sample_index)
            if recorded_at >= now:
                continue
            readings.append(
                TelemetryReading(
                    device_id=device.id,
                    event_id=f"demo-irrigation-{day:%Y%m%d}-{sample_index:02d}",
                    recorded_at=recorded_at,
                    received_at=now,
                    flow_rate_liters_minute=rate,
                    quality="valid",
                    battery_percent=84,
                    signal_dbm=-63 - (day.toordinal() % 10),
                    firmware_version="0.4.2-demo",
                )
            )
    return readings


async def _add_sample_alerts(
    session: AsyncSession,
    property_row: Property,
    device: Device,
    offline_device: Device,
    now: datetime,
) -> bool:
    existing = list(
        (
            await session.scalars(
                select(AnomalyEvent).where(AnomalyEvent.property_id == property_row.id)
            )
        ).all()
    )
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
        session.add(
            Alert(
                anomaly_id=anomaly.id,
                status=status,
                channel="dashboard",
                created_at=anomaly.detected_at,
                acknowledged_at=acknowledged,
                resolved_at=resolved,
            )
        )
        added = True
    return added


def _continuous_flow_readings(device: Device, now: datetime) -> list[TelemetryReading]:
    aligned_now = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    start = aligned_now - timedelta(hours=6)
    readings: list[TelemetryReading] = []
    for index in range(73):
        recorded_at = start + timedelta(minutes=5 * index)
        readings.append(
            TelemetryReading(
                device_id=device.id,
                event_id=f"demo-flow-{recorded_at:%Y%m%d%H%M}",
                recorded_at=recorded_at,
                received_at=now,
                flow_rate_liters_minute=Decimal("0.2"),
                quality="valid",
                battery_percent=83,
                signal_dbm=-61,
                firmware_version="0.4.2-demo",
            )
        )
    return readings


def _health_readings(devices: dict[str, Device], now: datetime) -> list[TelemetryReading]:
    """Add one zero-flow heartbeat per five-minute slot for active demo meters."""
    recorded_at = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    return [
        TelemetryReading(
            device_id=devices[serial].id,
            event_id=f"demo-health-{serial}-{recorded_at:%Y%m%d%H%M}",
            recorded_at=recorded_at,
            received_at=now,
            flow_rate_liters_minute=Decimal("0"),
            quality="valid",
            battery_percent=battery,
            signal_dbm=signal,
            firmware_version="0.4.2-demo",
        )
        for serial, battery, signal in (
            ("AF-DEMO-001", 92, -52),
            ("AF-DEMO-004", 78, -68),
        )
    ]


def _offline_reading(
    device: Device, recorded_at: datetime, received_at: datetime
) -> TelemetryReading:
    """Keep the stale meter's last reported sample consistent with its health state."""
    return TelemetryReading(
        device_id=device.id,
        event_id=f"demo-offline-{device.serial_number}-{recorded_at:%Y%m%d%H%M}",
        recorded_at=recorded_at,
        received_at=received_at,
        flow_rate_liters_minute=Decimal("0"),
        quality="valid",
        battery_percent=31,
        signal_dbm=-79,
        firmware_version="0.4.1-demo",
    )


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
