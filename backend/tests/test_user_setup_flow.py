import pytest
from httpx import AsyncClient


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
        json={"name": "Casa"},
    )
    assert created_property.status_code == 201
    property_body = created_property.json()
    assert property_body["timezone"] == "America/Sao_Paulo"
    assert property_body["volume_unit"] == "L"

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
