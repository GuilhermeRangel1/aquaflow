"""Hybrid demo history extension: grid alignment, afternoon uses and raw-data immutability."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import TelemetryReading, User
from app.demo_seed import _seed_hybrid_property

ZONE = ZoneInfo("America/Sao_Paulo")
# 18:03 local time: the last 24 h include the 16:10 and 17:10 afternoon uses.
NOW = datetime(2026, 11, 20, 21, 3, tzinfo=UTC)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _write_dataset(path: Path) -> Path:
    """Two local days of normal readings every 5 min; flow only between 07:00 and 07:30."""
    lines = [
        "recorded_at,reading_present,event_id,cumulative_volume_liters,"
        "flow_rate_liters_minute,battery_percent,signal_dbm,firmware_version,scenario_label"
    ]
    start = datetime(2026, 9, 1, 0, 0, tzinfo=ZONE)
    cumulative = Decimal("1000")
    for slot in range(2 * 288):
        local = start + timedelta(minutes=5 * slot)
        flow = Decimal("2.0") if local.hour == 7 and local.minute < 30 else Decimal("0")
        cumulative += flow * 5
        lines.append(
            f"{local.astimezone(UTC).isoformat()},1,e{slot},{cumulative},{flow},88,-55,hybrid,normal"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest_asyncio.fixture
async def seeded(tmp_path: Path) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], Path]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    dataset = _write_dataset(tmp_path / "hybrid.csv")
    async with sessions() as session:
        session.add(
            User(name="Administração", email="admin@admin.com", password_hash="x", created_at=NOW)
        )
        await session.commit()
    try:
        yield sessions, dataset
    finally:
        await engine.dispose()


async def _run(sessions: async_sessionmaker[AsyncSession], dataset: Path, now: datetime) -> bool:
    async with sessions() as session:
        user = (await session.scalars(select(User))).one()
        changed = await _seed_hybrid_property(session, user, dataset, now)
        await session.commit()
        return changed


async def _snapshot(
    sessions: async_sessionmaker[AsyncSession],
) -> dict[str, tuple[datetime, Decimal | None, Decimal | None]]:
    async with sessions() as session:
        readings = (await session.scalars(select(TelemetryReading))).all()
        return {
            r.event_id: (
                _utc(r.recorded_at),
                r.flow_rate_liters_minute,
                r.cumulative_volume_liters,
            )
            for r in readings
        }


@pytest.mark.asyncio
async def test_extension_fills_last_day_on_grid_with_afternoon_uses(seeded) -> None:
    sessions, dataset = seeded
    assert await _run(sessions, dataset, NOW)

    readings = sorted((await _snapshot(sessions)).items(), key=lambda item: item[1][0])
    extension = [
        (key, value) for key, value in readings if key.startswith("demo-hybrid-extension-")
    ]
    assert extension, "a extensão das últimas 24 h deveria ter sido criada"
    for _, (recorded_at, _, _) in extension:
        assert recorded_at.second == 0 and recorded_at.microsecond == 0
        assert recorded_at.minute % 5 == 0
    assert extension[-1][1][0] == NOW.replace(minute=0)  # 18:00 local, last full slot

    by_local = {value[0].astimezone(ZONE).strftime("%d %H:%M"): value for _, value in extension}
    assert by_local["20 16:10"][1] == Decimal("1.4")
    assert by_local["20 17:10"][1] == Decimal("0.8")

    cumulative = [value[2] for _, value in readings]
    assert all(after >= before for before, after in zip(cumulative, cumulative[1:], strict=False))


@pytest.mark.asyncio
async def test_rerun_at_same_time_changes_nothing(seeded) -> None:
    sessions, dataset = seeded
    assert await _run(sessions, dataset, NOW)
    before = await _snapshot(sessions)

    assert not await _run(sessions, dataset, NOW)
    assert await _snapshot(sessions) == before


@pytest.mark.asyncio
async def test_skipped_uses_are_never_applied_retroactively(seeded) -> None:
    """A real reading suppresses simulated uses; a later run must not rewrite those rows."""
    sessions, dataset = seeded
    first = datetime(2026, 11, 20, 18, 3, tzinfo=UTC)  # 15:03 local
    assert await _run(sessions, dataset, first)
    async with sessions() as session:
        device_id = (await session.scalars(select(TelemetryReading.device_id))).first()
        session.add(
            TelemetryReading(
                device_id=device_id,
                event_id="physical-reading-1",
                recorded_at=datetime(2026, 11, 20, 17, 0, tzinfo=UTC),  # 14:00 local
                received_at=first,
                cumulative_volume_liters=Decimal("1300"),
                flow_rate_liters_minute=Decimal("0.5"),
                quality="valid",
            )
        )
        await session.commit()

    # 16:33 local: the 16:10 slot is created while the real reading is inside the window.
    assert await _run(sessions, dataset, datetime(2026, 11, 20, 19, 33, tzinfo=UTC))
    before = await _snapshot(sessions)
    slot_1610 = next(
        value
        for key, value in before.items()
        if key.startswith("demo-hybrid-extension-")
        and value[0].astimezone(ZONE).strftime("%d %H:%M") == "20 16:10"
    )
    assert slot_1610[1] == Decimal("0")

    # Next day, 14:33 local: the real reading left the window, the 16:10 row did not.
    assert await _run(sessions, dataset, datetime(2026, 11, 21, 17, 33, tzinfo=UTC))
    after = await _snapshot(sessions)
    for event_id, value in before.items():
        assert after[event_id] == value, f"leitura persistida foi alterada: {event_id}"


@pytest.mark.asyncio
async def test_later_run_appends_without_rewriting_persisted_readings(seeded) -> None:
    sessions, dataset = seeded
    assert await _run(sessions, dataset, NOW)
    before = await _snapshot(sessions)
    latest_before = max(value[0] for value in before.values())

    later = NOW + timedelta(hours=1)
    assert await _run(sessions, dataset, later)
    after = await _snapshot(sessions)

    for event_id, value in before.items():
        assert after[event_id] == value, f"leitura persistida foi alterada: {event_id}"
    added = {key: value for key, value in after.items() if key not in before}
    assert added and all(value[0] > latest_before for value in added.values())
    async with sessions() as session:
        total = await session.scalar(select(func.count(TelemetryReading.id)))
    assert total == len(before) + len(added)
