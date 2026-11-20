from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


def _reading(event_id: str) -> dict[str, object]:
    return {
        "device_serial": "TEST-DEVICE-001",
        "event_id": event_id,
        "recorded_at": datetime.now(UTC).isoformat(),
        "cumulative_volume_liters": 10.0,
    }


@pytest.mark.asyncio
async def test_archive_hides_property_and_stops_ingestion(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    headers = {"Authorization": f"Bearer {token}"}

    archived = await client.delete(f"/api/v1/properties/{property_id}", headers=headers)
    again = await client.delete(f"/api/v1/properties/{property_id}", headers=headers)

    assert archived.status_code == 204
    assert again.status_code == 204
    listing = await client.get("/api/v1/properties", headers=headers)
    assert listing.json()["items"] == []
    for path in (
        f"/api/v1/properties/{property_id}",
        f"/api/v1/properties/{property_id}/dashboard-health",
        f"/api/v1/properties/{property_id}/alerts",
        f"/api/v1/properties/{property_id}/anomalies",
        f"/api/v1/properties/{property_id}/ml-inferences",
    ):
        assert (await client.get(path, headers=headers)).status_code == 404, path
    assert (await client.get("/api/v1/devices", headers=headers)).json()["items"] == []
    ingestion = await client.post(
        "/api/v1/ingestion/telemetry",
        headers={"X-Device-Key": device_key},
        json=_reading("after-archive"),
    )
    assert ingestion.status_code == 401


@pytest.mark.asyncio
async def test_archive_requires_ownership_and_auth(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client

    assert (await client.delete(f"/api/v1/properties/{property_id}")).status_code == 401
    unknown = await client.delete(
        f"/api/v1/properties/{uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_administration_house_cannot_be_archived(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, _, _, token = api_client
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post(
        "/api/v1/properties", headers=headers, json={"name": "Casa da Administração"}
    )
    protected_id = created.json()["id"]
    device = await client.post(
        "/api/v1/devices",
        headers=headers,
        json={
            "property_id": protected_id,
            "serial_number": "AF-DEMO-HIBRIDO-001",
            "name": "Medidor híbrido",
        },
    )

    response = await client.delete(f"/api/v1/properties/{protected_id}", headers=headers)

    assert device.status_code == 201
    assert response.status_code == 409
    assert response.json()["code"] == "property_archive_protected"
