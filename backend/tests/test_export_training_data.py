"""Tests for the real-telemetry training exporter."""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Device, Property, TelemetryReading, User
from app.export_training_data import (
    load_label_sheet,
    export,
)

SAO_PAULO = "America/Sao_Paulo"


def _write_sheet(path: Path, rows: Sequence[str]) -> Path:
    header = "corrida,device_serial,inicio_local,fim_local,cenario,obs\n"
    path.write_text(header + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


# --- load_label_sheet (pure, no database) ---------------------------------


def test_load_converts_local_window_to_utc(tmp_path: Path) -> None:
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        ["1,AF-ESP32-001,2026-11-20 14:02,2026-11-20 14:08,normal,uso curto"],
    )
    windows = load_label_sheet(sheet, SAO_PAULO)
    assert len(windows) == 1
    window = windows[0]
    # America/Sao_Paulo is UTC-3, so 14:02 local -> 17:02 UTC.
    assert window.start_utc == datetime(2026, 11, 20, 17, 2, tzinfo=UTC)
    assert window.end_utc == datetime(2026, 11, 20, 17, 8, tzinfo=UTC)
    assert window.scenario_label == "normal"
    assert window.anomaly_label == 0


def test_anomaly_label_is_one_for_non_normal(tmp_path: Path) -> None:
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        [
            "1,AF-1,2026-11-20 14:00,2026-11-20 14:05,continuous_flow,",
            "2,AF-1,2026-11-20 14:06,2026-11-20 14:10,night_consumption,",
        ],
    )
    windows = load_label_sheet(sheet, SAO_PAULO)
    assert [w.anomaly_label for w in windows] == [1, 1]


def test_invalid_scenario_is_rejected(tmp_path: Path) -> None:
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        ["1,AF-1,2026-11-20 14:00,2026-11-20 14:05,vazamento,"],
    )
    with pytest.raises(ValueError, match="cen"):
        load_label_sheet(sheet, SAO_PAULO)


def test_end_before_start_is_rejected(tmp_path: Path) -> None:
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        ["1,AF-1,2026-11-20 14:10,2026-11-20 14:05,normal,"],
    )
    with pytest.raises(ValueError, match="fim"):
        load_label_sheet(sheet, SAO_PAULO)


def test_bad_time_format_is_rejected(tmp_path: Path) -> None:
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        ["1,AF-1,20/11/2026 14h,2026-11-20 14:05,normal,"],
    )
    with pytest.raises(ValueError, match="hor"):
        load_label_sheet(sheet, SAO_PAULO)


def test_overlapping_windows_same_device_are_rejected(tmp_path: Path) -> None:
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        [
            "1,AF-1,2026-11-20 14:00,2026-11-20 14:10,normal,",
            "2,AF-1,2026-11-20 14:05,2026-11-20 14:15,continuous_flow,",
        ],
    )
    with pytest.raises(ValueError, match="sobrep"):
        load_label_sheet(sheet, SAO_PAULO)


def test_same_window_on_different_devices_is_allowed(tmp_path: Path) -> None:
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        [
            "1,AF-1,2026-11-20 14:00,2026-11-20 14:10,normal,",
            "2,AF-2,2026-11-20 14:00,2026-11-20 14:10,normal,",
        ],
    )
    windows = load_label_sheet(sheet, SAO_PAULO)
    assert len(windows) == 2


# --- export (reads the database) ------------------------------------------


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed_device(
    factory: async_sessionmaker[AsyncSession],
    serial: str,
    readings: Sequence[tuple[str, datetime, Decimal | None, Decimal | None]],
) -> None:
    now = datetime.now(UTC)
    async with factory.begin() as session:
        user = User(
            name=f"Owner {serial}",
            email=f"{serial.lower()}@example.test",
            password_hash="x",
            created_at=now,
        )
        session.add(user)
        await session.flush()
        prop = Property(
            owner_id=user.id,
            name=f"Casa {serial}",
            timezone=SAO_PAULO,
            volume_unit="L",
            created_at=now,
        )
        session.add(prop)
        await session.flush()
        device = Device(
            property_id=prop.id,
            serial_number=serial,
            name=f"Medidor {serial}",
            device_key_hash="x",
            expected_interval_seconds=300,
        )
        session.add(device)
        await session.flush()
        for event_id, recorded_at, cumulative, flow in readings:
            session.add(
                TelemetryReading(
                    device_id=device.id,
                    event_id=event_id,
                    recorded_at=recorded_at,
                    received_at=now,
                    cumulative_volume_liters=cumulative,
                    flow_rate_liters_minute=flow,
                    quality="valid",
                )
            )


def _utc(hour: int, minute: int) -> datetime:
    return datetime(2026, 11, 20, hour, minute, tzinfo=UTC)


@pytest.mark.asyncio
async def test_export_labels_only_readings_in_window(
    tmp_path: Path, sessions: async_sessionmaker[AsyncSession]
) -> None:
    # Window 14:00-14:10 local == 17:00-17:10 UTC.
    await _seed_device(
        sessions,
        "AF-1",
        [
            ("before", _utc(16, 58), Decimal("1000.000"), Decimal("0.100")),
            ("inside-1", _utc(17, 2), Decimal("1000.500"), Decimal("0.250")),
            ("inside-2", _utc(17, 8), Decimal("1001.000"), Decimal("0.300")),
            ("after", _utc(17, 20), Decimal("1002.000"), Decimal("0.100")),
        ],
    )
    # A different device inside the same clock window must be ignored.
    await _seed_device(
        sessions, "AF-2", [("other", _utc(17, 5), Decimal("5.000"), Decimal("9.900"))]
    )
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        ["1,AF-1,2026-11-20 14:00,2026-11-20 14:10,continuous_flow,forte"],
    )
    output = tmp_path / "out" / "readings.csv"

    rows = await export(sessions, sheet, output, SAO_PAULO)

    event_ids = {row["event_id"] for row in rows}
    assert event_ids == {"inside-1", "inside-2"}
    for row in rows:
        assert row["scenario_label"] == "continuous_flow"
        assert row["anomaly_label"] == 1
        assert row["corrida"] == "1"
        assert row["device_serial"] == "AF-1"
        assert row["recorded_at"].endswith("Z")
    assert output.exists()
    written = output.read_text(encoding="utf-8").splitlines()
    assert written[0] == (
        "corrida,device_serial,event_id,recorded_at,"
        "cumulative_volume_liters,flow_rate_liters_minute,quality,"
        "scenario_label,anomaly_label"
    )
    assert len(written) == 3  # header + 2 readings


@pytest.mark.asyncio
async def test_missing_reading_window_yields_no_rows(
    tmp_path: Path, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_device(
        sessions, "AF-1", [("outside", _utc(18, 0), None, Decimal("0.000"))]
    )
    sheet = _write_sheet(
        tmp_path / "rotulos.csv",
        ["1,AF-1,2026-11-20 14:00,2026-11-20 14:10,missing_reading,fio removido"],
    )
    output = tmp_path / "readings.csv"

    rows = await export(sessions, sheet, output, SAO_PAULO)

    assert rows == []
    assert output.exists()
    assert output.read_text(encoding="utf-8").splitlines()[1:] == []
