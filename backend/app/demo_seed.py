"""Populate the local demonstration with the calibrated dataset."""

import asyncio
import csv
import re
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import hash_device_key, hash_password
from app.db.models import Alert, AnomalyEvent, Device, MLInference, Property, TelemetryReading, User
from app.db.session import create_session_factory
from app.services.audit import add_audit_entry

DEMO_EMAIL = "demo@example.com"
ADMIN_EMAIL = "admin@admin.com"
LEGACY_ADMIN_EMAIL = "admin@example.com"
LEGACY_DEMO_EMAIL = "demo@aquaflow.local"
PROPERTY_TIMEZONE = "America/Sao_Paulo"
# Short normal uses added to the simulated afternoon of the demo extension (local time).
AFTERNOON_USES = {(16, 10): Decimal("1.4"), (17, 10): Decimal("0.8")}
LEGACY_SERIALS = {"AF-DEMO-001", "AF-DEMO-002", "AF-DEMO-003", "AF-DEMO-004", "AF-DEMO-ML-001"}
LEGACY_EVENT = re.compile(
    r"demo-(?:history-\d{8}-.+|\d{8}-.+|irrigation-\d{8}-\d+|flow-\d{12}|"
    r"health-AF-DEMO-[\w-]+-\d{12}|ml-showcase-(?:baseline|normal|peak-[12]))"
)


async def seed_demo_data(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    password: str,
    email: str | None = None,
    dataset_path: Path,
    cleanup_legacy: bool = False,
) -> bool:
    """Populate the demo history; legacy fixtures are only migrated/removed on request."""
    configured_email = email or ADMIN_EMAIL
    async with session_factory() as session:
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        user = await session.scalar(select(User).where(User.email == configured_email))
        if user is None and cleanup_legacy and configured_email == ADMIN_EMAIL:
            user = await session.scalar(
                select(User)
                .join(Property, Property.owner_id == User.id)
                .join(Device, Device.property_id == Property.id)
                .where(
                    User.email.in_((LEGACY_ADMIN_EMAIL, DEMO_EMAIL, LEGACY_DEMO_EMAIL)),
                    Device.serial_number == "AF-DEMO-HIBRIDO-001",
                )
            )
        if user is None and cleanup_legacy:
            user = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None and cleanup_legacy:
            user = await session.scalar(select(User).where(User.email == LEGACY_DEMO_EMAIL))
        if user is not None and user.email != configured_email:
            if configured_email == ADMIN_EMAIL and user.name in (
                "Administração",
                "Conta de demonstração",
            ):
                user.password_hash = hash_password(password)
            user.email = configured_email
        created = user is None
        if user is None:
            user = User(
                name="Administração",
                email=configured_email,
                password_hash=hash_password(password),
                created_at=now,
            )
            session.add(user)
            await session.flush()

        if user.name == "Conta de demonstração":
            user.name = "Administração"
        populated = await _seed_hybrid_property(session, user, dataset_path, now)
        removed = await _remove_legacy_fixtures(session, user) if cleanup_legacy else False
        await session.commit()
        return populated or removed or created


async def _seed_hybrid_property(
    session: AsyncSession, user: User, dataset_path: Path, now: datetime
) -> bool:
    name = "Casa da Administração"
    serial = "AF-DEMO-PRINCIPAL-001"
    legacy_serial = "AF-DEMO-HIBRIDO-001"
    property_row = await session.scalar(
        select(Property).where(Property.owner_id == user.id, Property.name == name)
    )
    device = await session.scalar(select(Device).where(Device.serial_number == serial))
    if device is None:
        device = await session.scalar(select(Device).where(Device.serial_number == legacy_serial))
    if device is not None:
        if property_row is None:
            property_row = await session.scalar(
                select(Property).where(
                    Property.id == device.property_id,
                    Property.owner_id == user.id,
                    Property.name == "Casa da demonstração híbrida",
                )
            )
            if property_row is not None:
                property_row.name = name
        if property_row is None or device.property_id != property_row.id:
            raise RuntimeError("Medidor de demonstração pertence a outra propriedade.")
        device.serial_number = serial
    with dataset_path.open(newline="", encoding="utf-8") as source:
        rows = [
            (datetime.fromisoformat(row["recorded_at"]), row)
            for row in csv.DictReader(source)
            if row["reading_present"] == "1"
        ]
    if not rows:
        raise ValueError("Dataset da demonstração sem leituras.")
    if device is not None:
        latest = await session.scalar(
            select(TelemetryReading)
            .where(TelemetryReading.device_id == device.id)
            .order_by(TelemetryReading.recorded_at.desc())
            .limit(1)
        )
        if latest is not None:
            add_uses = not await _has_recent_non_demo_reading(session, device, now)
            return _extend_hybrid_history(session, device, latest, rows, now, add_uses=add_uses)
    zone = ZoneInfo(PROPERTY_TIMEZONE)
    shift = now.astimezone(zone).date() - rows[-1][0].astimezone(zone).date()
    # Reserve the recent window for the normal-use profile on the first startup too.
    # Smaller fixtures without a normal profile retain their original import behavior.
    readings = [(timestamp + shift, row) for timestamp, row in rows if timestamp + shift <= now]
    if any(row.get("scenario_label") == "normal" for _, row in rows):
        recent_start = now - timedelta(hours=24)
        historical = [(timestamp, row) for timestamp, row in readings if timestamp < recent_start]
        if historical:
            readings = historical
    if not readings:
        raise ValueError("Dataset da demonstração sem leituras até o horário atual.")
    if property_row is None:
        property_row = Property(
            owner_id=user.id,
            name=name,
            timezone=PROPERTY_TIMEZONE,
            volume_unit="L",
            created_at=now,
        )
        session.add(property_row)
        await session.flush()
    if device is None:
        device = _device(
            property_row.id,
            serial,
            "Medidor principal",
            now,
            last_seen_at=readings[-1][0],
        )
        session.add(device)
        await session.flush()
    historical_readings = [
        TelemetryReading(
            device_id=device.id,
            event_id=f"demo-calibrado-v1-{row['event_id']}",
            recorded_at=timestamp,
            received_at=now,
            cumulative_volume_liters=Decimal(row["cumulative_volume_liters"]),
            flow_rate_liters_minute=Decimal(row["flow_rate_liters_minute"]),
            quality="valid",
            battery_percent=int(row["battery_percent"]),
            signal_dbm=int(row["signal_dbm"]),
            firmware_version=row["firmware_version"],
        )
        for timestamp, row in readings
    ]
    session.add_all(historical_readings)
    _extend_hybrid_history(session, device, historical_readings[-1], rows, now, add_uses=True)
    return True


def _extend_hybrid_history(
    session: AsyncSession,
    device: Device,
    latest: TelemetryReading,
    rows: list[tuple[datetime, dict[str, str]]],
    now: datetime,
    *,
    add_uses: bool,
) -> bool:
    if not latest.event_id.startswith(("demo-hybrid-", "demo-calibrado-")):
        return False
    zone = ZoneInfo(PROPERTY_TIMEZONE)
    profiles: dict[date, dict[tuple[int, int], Decimal]] = {}
    for timestamp, row in rows:
        if row.get("scenario_label") != "normal":
            continue
        local = timestamp.astimezone(zone)
        profiles.setdefault(local.date(), {})[local.hour, local.minute] = Decimal(
            row["flow_rate_liters_minute"]
        )
    if not profiles or latest.cumulative_volume_liters is None:
        return False

    profile = max(profiles.values(), key=len)
    interval = timedelta(minutes=5)
    end = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)
    previous = latest.recorded_at
    previous = previous.replace(tzinfo=UTC) if previous.tzinfo is None else previous
    start = previous + interval
    timestamp = max(start, end - timedelta(hours=24))
    cumulative = latest.cumulative_volume_liters
    if timestamp > end:
        return False
    while timestamp <= end:
        local = timestamp.astimezone(zone)
        flow = profile.get((local.hour, local.minute // 5 * 5), Decimal(0))
        if flow == 0 and add_uses:
            # Short afternoon uses are part of the new reading itself; persisted
            # readings are never rewritten (raw telemetry stays traceable).
            flow = AFTERNOON_USES.get((local.hour, local.minute), flow)
        cumulative += flow * 5
        session.add(
            TelemetryReading(
                device_id=device.id,
                event_id=f"demo-calibrado-extension-{timestamp:%Y%m%d%H%M}",
                recorded_at=timestamp,
                received_at=now,
                cumulative_volume_liters=cumulative,
                flow_rate_liters_minute=flow,
                quality="valid",
            )
        )
        timestamp += interval
    device.last_seen_at = timestamp - interval
    return True


async def _has_recent_non_demo_reading(
    session: AsyncSession, device: Device, now: datetime
) -> bool:
    """Real telemetry in the last 24 h means no simulated uses are added."""
    return (
        await session.scalar(
            select(TelemetryReading.id)
            .where(
                TelemetryReading.device_id == device.id,
                TelemetryReading.recorded_at >= now - timedelta(hours=24),
                TelemetryReading.event_id.not_like("demo-hybrid-%"),
                TelemetryReading.event_id.not_like("demo-calibrado-%"),
            )
            .limit(1)
        )
        is not None
    )


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


async def _remove_legacy_fixtures(session: AsyncSession, user: User) -> bool:
    legacy = await session.scalar(
        select(Property).where(
            Property.owner_id == user.id,
            Property.name == "Casa da demonstração",
        )
    )
    if legacy is None:
        return False
    devices = list(await session.scalars(select(Device).where(Device.property_id == legacy.id)))
    removed = 0
    for device in devices:
        if device.serial_number not in LEGACY_SERIALS:
            continue
        ids = await session.scalars(
            select(TelemetryReading.event_id).where(
                TelemetryReading.device_id == device.id,
            )
        )
        if any(not LEGACY_EVENT.fullmatch(event_id) for event_id in ids):
            continue
        readings = select(TelemetryReading.id).where(TelemetryReading.device_id == device.id)
        anomalies = select(AnomalyEvent.id).where(AnomalyEvent.device_id == device.id)
        await session.execute(delete(MLInference).where(MLInference.reading_id.in_(readings)))
        await session.execute(delete(Alert).where(Alert.anomaly_id.in_(anomalies)))
        await session.execute(delete(AnomalyEvent).where(AnomalyEvent.device_id == device.id))
        await session.execute(
            delete(TelemetryReading).where(TelemetryReading.device_id == device.id)
        )
        add_audit_entry(
            session,
            actor_id=user.id,
            action="device.deleted",
            resource_type="device",
            resource_id=device.id,
            metadata={"reason": "legacy_demo_fixtures_removed"},
        )
        await session.delete(device)
        removed += 1
    if removed and removed == len(devices):
        await session.flush()
        await session.delete(legacy)
    return bool(removed)


async def main() -> None:
    if not settings.demo_mode:
        return
    if settings.demo_dataset_path is None:
        raise RuntimeError("Configure DEMO_DATASET_PATH com a série calibrada.")
    factory = create_session_factory(settings)
    try:
        created = await seed_demo_data(
            factory,
            password=settings.demo_user_password,
            email=settings.demo_user_email or ADMIN_EMAIL,
            dataset_path=settings.demo_dataset_path,
            cleanup_legacy=settings.demo_cleanup_legacy,
        )
        if created:
            print("Histórico de demonstração preparado.")
        else:
            print("Histórico de demonstração já está atualizado.")
    finally:
        bind = factory.kw.get("bind")
        if bind is not None:
            await bind.dispose()


if __name__ == "__main__":
    asyncio.run(main())
