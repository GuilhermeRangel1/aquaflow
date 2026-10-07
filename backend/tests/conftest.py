from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import hash_device_key, issue_access_token
from app.db.base import Base
from app.db.models import Device, Property, User
from app.main import create_app


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[tuple[AsyncClient, UUID, str, str]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="test-only-secret-with-enough-entropy-for-tests",
    )
    app = create_app(settings=settings, session_factory=sessions)

    user_id = uuid4()
    property_id = uuid4()
    device_id = uuid4()
    device_key = "test-device-key-never-used-outside-tests"
    async with sessions.begin() as session:
        session.add(
            User(
                id=user_id,
                name="Test Owner",
                email="owner@example.test",
                password_hash="test-password-hash",
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            Property(
                id=property_id,
                owner_id=user_id,
                name="Casa de teste",
                timezone="America/Sao_Paulo",
                volume_unit="L",
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            Device(
                id=device_id,
                property_id=property_id,
                serial_number="TEST-DEVICE-001",
                name="Medidor de teste",
                device_key_hash=hash_device_key(device_key),
                expected_interval_seconds=300,
            )
        )

    token = issue_access_token(user_id, settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, property_id, device_key, token
    await engine.dispose()


def reading_payload(
    event_id: str,
    recorded_at: str,
    *,
    cumulative_volume_liters: float | None = None,
    flow_rate_liters_minute: float | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "device_serial": "TEST-DEVICE-001",
        "event_id": event_id,
        "recorded_at": recorded_at,
    }
    if cumulative_volume_liters is not None:
        payload["cumulative_volume_liters"] = cumulative_volume_liters
    if flow_rate_liters_minute is not None:
        payload["flow_rate_liters_minute"] = flow_rate_liters_minute
    return payload


@pytest_asyncio.fixture
async def empty_api_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="test-only-secret-with-enough-entropy-for-tests",
    )
    app = create_app(settings=settings, session_factory=sessions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await engine.dispose()
