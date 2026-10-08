from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import Alert, Device, Property, TelemetryReading, User
from app.demo_seed import DEMO_EMAIL, LEGACY_DEMO_EMAIL, seed_demo_data
from app.main import create_app


@pytest.mark.asyncio
async def test_demo_dataset_is_idempotent_and_visible_through_public_api() -> None:
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
        session.add(User(
            name="Conta de demonstração",
            email=LEGACY_DEMO_EMAIL,
            password_hash=hash_password(password),
            created_at=datetime.now(UTC),
        ))
        await session.commit()
    assert await seed_demo_data(sessions, password=password) is True
    assert await seed_demo_data(sessions, password=password) is False

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Property)) == 1
        assert await session.scalar(select(func.count()).select_from(Device)) == 4
        assert await session.scalar(select(func.count()).select_from(TelemetryReading)) >= 150
        assert await session.scalar(select(func.count()).select_from(Alert)) == 5

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="test-only-secret-with-enough-entropy-for-tests",
    )
    app = create_app(settings=settings, session_factory=sessions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": DEMO_EMAIL, "password": password},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}
        properties = await client.get("/api/v1/properties", headers=headers)
        devices = await client.get("/api/v1/devices", headers=headers)
        property_id = properties.json()["items"][0]["id"]
        alerts = await client.get(f"/api/v1/properties/{property_id}/alerts", headers=headers)
        end = datetime.now(UTC)
        start = end - timedelta(days=7)
        consumption = await client.get(
            f"/api/v1/properties/{property_id}/consumption",
            params={"start": start.isoformat(), "end": end.isoformat(), "granularity": "day"},
            headers=headers,
        )

    assert properties.status_code == devices.status_code == alerts.status_code == 200
    assert len(properties.json()["items"]) == 1
    assert len(devices.json()["items"]) == 4
    assert any(device["last_seen_at"] is None for device in devices.json()["items"])
    assert {alert["status"] for alert in alerts.json()["items"]} == {
        "open", "acknowledged", "resolved", "false_positive"
    }
    sample_alerts = [
        alert for alert in alerts.json()["items"] if alert["evidence"].get("is_demo_sample")
    ]
    assert any(
        alert["detector_type"] == "night_consumption"
        and alert["evidence"].get("timezone") == "America/Sao_Paulo"
        for alert in sample_alerts
    )
    assert any(
        alert["detector_type"] == "device_offline"
        and alert["evidence"].get("offline_threshold_seconds") == 600
        for alert in sample_alerts
    )
    assert consumption.status_code == 200
    assert consumption.json()["summary"]["total_volume_liters"] > 0
    await engine.dispose()
