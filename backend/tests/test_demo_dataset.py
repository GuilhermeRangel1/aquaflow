from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Device, Property, TelemetryReading, User
from app.demo_seed import ADMIN_EMAIL, LEGACY_DEMO_EMAIL, seed_demo_data
from app.main import create_app


@pytest.mark.asyncio
async def test_demo_dataset_is_idempotent_and_visible_through_public_api(tmp_path: Path) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    password = "Demo-only-test-password-123!"
    async with sessions() as session:
        session.add(
            User(
                name="Conta de demonstração",
                email=LEGACY_DEMO_EMAIL,
                password_hash=hash_password(password),
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    now = datetime.now(UTC)
    dataset = tmp_path / "hybrid.csv"
    dataset.write_text(
        "recorded_at,reading_present,event_id,cumulative_volume_liters,"
        "flow_rate_liters_minute,battery_percent,signal_dbm,firmware_version\n"
        f"{(now - timedelta(minutes=5)).isoformat()},1,first,100,0,88,-55,hybrid\n"
        f"{(now - timedelta(minutes=2)).isoformat()},1,next,101,0.2,88,-55,hybrid\n",
        encoding="utf-8",
    )
    async with sessions() as session:
        user = (await session.scalars(select(User))).one()
        legacy = Property(owner_id=user.id, name="Casa da demonstração", created_at=now)
        session.add(legacy)
        await session.flush()
        for serial, event_id in (
            ("AF-DEMO-001", "demo-history-20260901-test-1"),
            ("ESP32-BANCADA", "physical-reading"),
        ):
            device = Device(
                property_id=legacy.id,
                serial_number=serial,
                name=serial,
                device_key_hash="0" * 64,
            )
            session.add(device)
            await session.flush()
            session.add(
                TelemetryReading(
                    device_id=device.id,
                    event_id=event_id,
                    recorded_at=now,
                    received_at=now,
                )
            )
        await session.commit()
    assert await seed_demo_data(
        sessions, password=password, dataset_path=dataset, cleanup_legacy=True
    )
    assert not await seed_demo_data(
        sessions, password=password, dataset_path=dataset, cleanup_legacy=True
    )
    async with sessions() as session:
        assert set(await session.scalars(select(TelemetryReading.event_id))) == {
            "demo-hybrid-v1-first",
            "demo-hybrid-v1-next",
            "physical-reading",
        }
    app = create_app(settings=Settings(), session_factory=sessions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": password},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}
        devices = (await client.get("/api/v1/devices", headers=headers)).json()["items"]
        assert {d["serial_number"] for d in devices} == {"AF-DEMO-HIBRIDO-001", "ESP32-BANCADA"}
        hybrid = next(d for d in devices if d["serial_number"] == "AF-DEMO-HIBRIDO-001")
        result = await client.get(f"/api/v1/devices/{hybrid['id']}/readings", headers=headers)
        assert result.status_code == 200
        assert {r["event_id"] for r in result.json()["items"]} == {
            "demo-hybrid-v1-first",
            "demo-hybrid-v1-next",
        }
    await engine.dispose()
