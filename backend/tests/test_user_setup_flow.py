from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import reading_payload


@pytest.mark.asyncio
async def test_owner_can_update_property_settings_through_public_api(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    headers = {"Authorization": f"Bearer {token}"}

    updated = await client.patch(
        f"/api/v1/properties/{property_id}",
        headers=headers,
        json={
            "name": "Casa de campo",
            "address": "Rua das Águas, 42",
            "timezone": "America/Manaus",
            "continuous_flow_threshold_liters_minute": 0.35,
            "continuous_flow_duration_minutes": 45,
            "late_reading_window_days": 12,
        },
    )
    retrieved = await client.get(f"/api/v1/properties/{property_id}", headers=headers)

    assert updated.status_code == 200
    assert updated.json()["timezone"] == "America/Manaus"
    assert Decimal(updated.json()["continuous_flow_threshold_liters_minute"]) == Decimal("0.35")
    assert updated.json()["continuous_flow_duration_minutes"] == 45
    assert updated.json()["late_reading_window_days"] == 12
    assert retrieved.status_code == 200
    assert retrieved.json()["name"] == "Casa de campo"
    assert retrieved.json()["address"] == "Rua das Águas, 42"


@pytest.mark.asyncio
async def test_owner_can_edit_and_retire_meter_without_losing_consumption_history(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    authorization = {"Authorization": f"Bearer {token}"}
    devices = await client.get("/api/v1/devices", headers=authorization)
    device_id = devices.json()["items"][0]["id"]
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    for event_id, recorded_at, volume in [
        (str(uuid4()), start, 80.0),
        (str(uuid4()), start + timedelta(minutes=5), 85.0),
    ]:
        accepted = await client.post(
            "/api/v1/ingestion/telemetry",
            headers={"X-Device-Key": device_key},
            json=reading_payload(
                event_id,
                recorded_at.isoformat(),
                cumulative_volume_liters=volume,
            ),
        )
        assert accepted.status_code == 202

    edited = await client.patch(
        f"/api/v1/devices/{device_id}",
        headers=authorization,
        json={"name": "Medidor da cozinha", "expected_interval_seconds": 600},
    )
    retired = await client.delete(f"/api/v1/devices/{device_id}", headers=authorization)
    listed_after_retirement = await client.get("/api/v1/devices", headers=authorization)
    consumption = await client.get(
        f"/api/v1/properties/{property_id}/consumption",
        params={
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "granularity": "hour",
        },
        headers=authorization,
    )

    assert edited.status_code == 200
    assert edited.json()["name"] == "Medidor da cozinha"
    assert edited.json()["expected_interval_seconds"] == 600
    assert retired.status_code == 204
    assert all(item["id"] != device_id for item in listed_after_retirement.json()["items"])
    assert consumption.status_code == 200
    assert consumption.json()["summary"]["total_volume_liters"] == pytest.approx(5.0)



@pytest.mark.asyncio
async def test_user_can_register_create_property_and_provision_device(
    empty_api_client: AsyncClient,
) -> None:
    registration = await empty_api_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Ana Silva",
            "email": "ana@example.com",
            "password": "A-long-test-only-password-123!",
        },
    )

    assert registration.status_code == 201
    registered = registration.json()
    assert registered["user"]["email"] == "ana@example.com"
    assert "password_hash" not in registered["user"]
    access_token = registered["tokens"]["access_token"]
    authorization = {"Authorization": f"Bearer {access_token}"}

    created_property = await empty_api_client.post(
        "/api/v1/properties",
        headers=authorization,
        json={
            "name": "Casa",
            "continuous_flow_threshold_liters_minute": 0.25,
            "continuous_flow_duration_minutes": 120,
        },
    )
    assert created_property.status_code == 201
    property_body = created_property.json()
    assert property_body["timezone"] == "America/Sao_Paulo"
    assert property_body["volume_unit"] == "L"
    assert Decimal(property_body["continuous_flow_threshold_liters_minute"]) == Decimal("0.25")
    assert property_body["continuous_flow_duration_minutes"] == 120

    created_device = await empty_api_client.post(
        "/api/v1/devices",
        headers=authorization,
        json={
            "property_id": property_body["id"],
            "serial_number": "ESP32-TEST-001",
            "name": "Medidor principal",
        },
    )
    assert created_device.status_code == 201
    device_body = created_device.json()
    assert device_body["expected_interval_seconds"] == 300
    assert device_body["device_key"].startswith("af_")
    assert "device_key_hash" not in device_body


@pytest.mark.asyncio
async def test_duplicate_registration_does_not_create_another_user(
    empty_api_client: AsyncClient,
) -> None:
    body = {
        "name": "Ana Silva",
        "email": "ana@example.com",
        "password": "A-long-test-only-password-123!",
    }
    first = await empty_api_client.post("/api/v1/auth/register", json=body)
    duplicate = await empty_api_client.post("/api/v1/auth/register", json=body)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "email_already_registered"


@pytest.mark.asyncio
async def test_property_and_device_lists_are_scoped_to_authenticated_owner(
    empty_api_client: AsyncClient,
) -> None:
    account = await empty_api_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Ana Silva",
            "email": "ana@example.com",
            "password": "A-long-test-only-password-123!",
        },
    )
    assert account.status_code == 201
    headers = {"Authorization": f"Bearer {account.json()['tokens']['access_token']}"}
    property_response = await empty_api_client.post(
        "/api/v1/properties", headers=headers, json={"name": "Casa"}
    )
    property_id = property_response.json()["id"]

    properties = await empty_api_client.get("/api/v1/properties", headers=headers)
    assert properties.status_code == 200
    assert [item["id"] for item in properties.json()["items"]] == [property_id]

    devices = await empty_api_client.get("/api/v1/devices", headers=headers)
    assert devices.status_code == 200
    assert devices.json()["items"] == []


@pytest.mark.asyncio
async def test_refresh_rotation_profile_update_and_logout(
    empty_api_client: AsyncClient,
) -> None:
    registration = await empty_api_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Ana Silva",
            "email": "ana@example.com",
            "password": "A-long-test-only-password-123!",
        },
    )
    tokens = registration.json()["tokens"]
    rotated = await empty_api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]

    reused = await empty_api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401

    headers = {"Authorization": f"Bearer {rotated.json()['access_token']}"}
    profile = await empty_api_client.patch(
        "/api/v1/auth/me", headers=headers, json={"name": "Ana S."}
    )
    assert profile.status_code == 200
    assert profile.json()["name"] == "Ana S."

    logout = await empty_api_client.post(
        "/api/v1/auth/logout",
        headers=headers,
        json={"refresh_token": rotated.json()["refresh_token"]},
    )
    assert logout.status_code == 204
    revoked = await empty_api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}
    )
    assert revoked.status_code == 401
