from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_meter_summary_is_empty_and_private(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    headers = {"Authorization": f"Bearer {token}"}
    devices = await client.get("/api/v1/devices", headers=headers)
    device_id = devices.json()["items"][0]["id"]
    path = f"/api/v1/devices/{device_id}/inference-summary"
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=headers)).json() == {
        "reading_id": None,
        "status": "no_reading",
        "latest_analysis": None,
    }
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Outra conta",
            "email": "other-summary@example.com",
            "password": "test-password-with-12",
        },
    )
    other_token = registration.json()["tokens"]["access_token"]
    assert (
        await client.get(path, headers={"Authorization": f"Bearer {other_token}"})
    ).status_code == 404
    history = f"/api/v1/devices/{device_id}/recent-analysis"
    assert (await client.get(history)).status_code == 401
    assert (await client.get(history, headers=headers)).json() == []
    assert (
        await client.get(history, headers={"Authorization": f"Bearer {other_token}"})
    ).status_code == 404


@pytest.mark.asyncio
async def test_owner_can_query_ml_inferences_for_property(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    response = await client.get(
        f"/api/v1/properties/{property_id}/ml-inferences",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 50, "cursor": None, "has_more": False}
    filtered = await client.get(
        f"/api/v1/properties/{property_id}/ml-inferences",
        params={"latest_for_reading_ids": str(uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["items"] == []


@pytest.mark.asyncio
async def test_ml_inferences_require_property_ownership(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    headers = {"Authorization": f"Bearer {token}"}

    unauthorized = await client.get(f"/api/v1/properties/{property_id}/ml-inferences")
    forbidden = await client.get(f"/api/v1/properties/{uuid4()}/ml-inferences", headers=headers)

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_ml_inferences_require_property_ownership_for_regular_accounts(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, _ = api_client
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Conta comum",
            "email": "viewer@example.net",
            "password": "test-password-with-12",
        },
    )
    assert registration.status_code == 201
    token = registration.json()["tokens"]["access_token"]
    response = await client.get(
        f"/api/v1/properties/{property_id}/ml-inferences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ml_inferences_validate_time_ranges_and_cursors(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    headers = {"Authorization": f"Bearer {token}"}
    invalid_range = await client.get(
        f"/api/v1/properties/{property_id}/ml-inferences",
        params={"start": "2026-11-20T10:00:00-03:00", "end": "2026-11-20T09:00:00-03:00"},
        headers=headers,
    )
    invalid_cursor = await client.get(
        f"/api/v1/properties/{property_id}/ml-inferences",
        params={"cursor": "not-a-cursor"},
        headers=headers,
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["code"] == "invalid_range"
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["code"] == "invalid_cursor"
