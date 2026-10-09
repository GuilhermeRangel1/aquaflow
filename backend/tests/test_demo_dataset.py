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
        session.add(
            User(
                name="Conta de demonstração",
                email=LEGACY_DEMO_EMAIL,
                password_hash=hash_password(password),
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    demo_email = f"custom-{DEMO_EMAIL}"
    assert await seed_demo_data(sessions, password=password, email=demo_email) is True
    assert await seed_demo_data(sessions, password=password, email=demo_email) is False

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Property)) == 1
        assert await session.scalar(select(func.count()).select_from(Device)) == 4
        assert await session.scalar(select(func.count()).select_from(TelemetryReading)) >= 900
        assert await session.scalar(select(func.count()).select_from(Alert)) == 5

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="test-only-secret-with-enough-entropy-for-tests",
    )
    app = create_app(settings=settings, session_factory=sessions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": demo_email, "password": password},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}
        properties = await client.get("/api/v1/properties", headers=headers)
        devices = await client.get("/api/v1/devices", headers=headers)
        property_id = properties.json()["items"][0]["id"]
        alerts = await client.get(
            f"/api/v1/properties/{property_id}/alerts",
            params={"limit": 2},
            headers=headers,
        )
        alert_pages = list(alerts.json()["items"])
        next_alert_cursor = alerts.json()["cursor"]
        assert alerts.json()["has_more"] is True
        assert next_alert_cursor
        while next_alert_cursor:
            next_page = await client.get(
                f"/api/v1/properties/{property_id}/alerts",
                params={"limit": 2, "cursor": next_alert_cursor},
                headers=headers,
            )
            assert next_page.status_code == 200
            alert_pages.extend(next_page.json()["items"])
            next_alert_cursor = next_page.json()["cursor"]

        anomalies = await client.get(
            f"/api/v1/properties/{property_id}/anomalies",
            params={"limit": 2},
            headers=headers,
        )
        anomaly_pages = list(anomalies.json()["items"])
        next_anomaly_cursor = anomalies.json()["cursor"]
        assert anomalies.json()["has_more"] is True
        while next_anomaly_cursor:
            next_page = await client.get(
                f"/api/v1/properties/{property_id}/anomalies",
                params={"limit": 2, "cursor": next_anomaly_cursor},
                headers=headers,
            )
            assert next_page.status_code == 200
            anomaly_pages.extend(next_page.json()["items"])
            next_anomaly_cursor = next_page.json()["cursor"]
        end = datetime.now(UTC)
        start = end - timedelta(days=7)
        consumption = await client.get(
            f"/api/v1/properties/{property_id}/consumption",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "granularity": "day",
                "limit": 2,
            },
            headers=headers,
        )
        second_consumption_page = await client.get(
            f"/api/v1/properties/{property_id}/consumption",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "granularity": "day",
                "limit": 2,
                "cursor": consumption.json()["cursor"],
            },
            headers=headers,
        )
        metrics = await client.get("/metrics")

    assert properties.status_code == devices.status_code == alerts.status_code == 200
    assert len(properties.json()["items"]) == 1
    assert len(devices.json()["items"]) == 4
    assert len(alert_pages) == 5
    assert len({alert["id"] for alert in alert_pages}) == 5
    assert len(anomaly_pages) >= 5
    assert len({anomaly["id"] for anomaly in anomaly_pages}) == len(anomaly_pages)
    offline_meter = next(
        device for device in devices.json()["items"] if device["serial_number"] == "AF-DEMO-003"
    )
    assert offline_meter["last_seen_at"] is not None
    offline_last_seen = datetime.fromisoformat(offline_meter["last_seen_at"])
    if offline_last_seen.tzinfo is None:
        offline_last_seen = offline_last_seen.replace(tzinfo=UTC)
    assert offline_last_seen < end - timedelta(minutes=10)
    assert {alert["status"] for alert in alert_pages} == {
        "open",
        "acknowledged",
        "resolved",
        "false_positive",
    }
    sample_alerts = [alert for alert in alert_pages if alert["evidence"].get("is_demo_sample")]
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
    assert consumption.json()["has_more"] is True
    assert consumption.json()["cursor"]
    assert second_consumption_page.status_code == 200
    assert (
        second_consumption_page.json()["items"][0]["bucket_start"]
        != consumption.json()["items"][0]["bucket_start"]
    )
    assert second_consumption_page.json()["summary"] == consumption.json()["summary"]
    assert metrics.status_code == 200
    assert "aquaflow_http_requests_total" in metrics.text
    await engine.dispose()
