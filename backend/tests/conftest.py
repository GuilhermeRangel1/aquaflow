import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import Settings
from app.core.security import hash_device_key, issue_access_token
from app.db.base import Base
from app.db.models import Device, Property, User
from app.main import create_app


@asynccontextmanager
async def _test_engine() -> AsyncIterator[AsyncEngine]:
    database_url = os.getenv("AQUAFLOW_TEST_DATABASE_URL")
    if not database_url:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            yield engine
        finally:
            await engine.dispose()
        return

    schema = f"aquaflow_test_{uuid4().hex}"
    admin_engine = create_async_engine(database_url, poolclass=NullPool)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[tuple[AsyncClient, UUID, str, str]]:
    async with _test_engine() as engine:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            database_url=os.getenv("AQUAFLOW_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"),
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
            await session.flush()
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
            await session.flush()
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
    async with _test_engine() as engine:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            database_url=os.getenv("AQUAFLOW_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"),
            jwt_secret="test-only-secret-with-enough-entropy-for-tests",
        )
        app = create_app(settings=settings, session_factory=sessions)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture
async def stale_meter_api_client() -> AsyncIterator[tuple[AsyncClient, UUID, str, str]]:
    async with _test_engine() as engine:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            database_url=os.getenv("AQUAFLOW_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"),
            jwt_secret="test-only-secret-with-enough-entropy-for-tests",
        )
        app = create_app(settings=settings, session_factory=sessions)
        user_id = uuid4()
        property_id = uuid4()
        device_id = uuid4()
        device_key = "stale-device-key-never-used-outside-tests"
        async with sessions.begin() as session:
            session.add(
                User(
                    id=user_id,
                    name="Offline Test Owner",
                    email="offline-owner@example.test",
                    password_hash="test-password-hash",
                    created_at=datetime.now(UTC),
                )
            )
            await session.flush()
            session.add(
                Property(
                    id=property_id,
                    owner_id=user_id,
                    name="Casa com medidor offline",
                    timezone="America/Sao_Paulo",
                    volume_unit="L",
                    created_at=datetime.now(UTC),
                )
            )
            await session.flush()
            session.add(
                Device(
                    id=device_id,
                    property_id=property_id,
                    serial_number="OFFLINE-TEST-001",
                    name="Medidor offline",
                    device_key_hash=hash_device_key(device_key),
                    expected_interval_seconds=300,
                    last_seen_at=datetime.now(UTC) - timedelta(minutes=20),
                )
            )

        token = issue_access_token(user_id, settings)
        transport = ASGITransport(app=app)
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0.05)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client, property_id, device_key, token
