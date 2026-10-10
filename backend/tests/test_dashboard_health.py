from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_health_requires_owned_property(
    api_client: tuple[AsyncClient, UUID, str, str],
) -> None:
    client, property_id, _, token = api_client
    headers = {"Authorization": f"Bearer {token}"}
    ingestion = await client.post(
        "/api/v1/ingestion/telemetry",
        headers={"X-Device-Key": api_client[2]},
        json={
            "device_serial": "TEST-DEVICE-001",
            "event_id": "dashboard-health-reading",
            "recorded_at": datetime.now(UTC).isoformat(),
            "cumulative_volume_liters": 12.5,
        },
    )

    response = await client.get(
        f"/api/v1/properties/{property_id}/dashboard-health", headers=headers
    )
    unauthorized = await client.get(f"/api/v1/properties/{property_id}/dashboard-health")
    other_property = await client.get(
        f"/api/v1/properties/{uuid4()}/dashboard-health", headers=headers
    )

    assert ingestion.status_code == 202
    assert response.status_code == 200
    body = response.json()
    assert body["ingestion"]["api_status"] == "healthy"
    assert body["ingestion"]["readings_last_24h"] == 1
    assert body["ingestion"]["mqtt_status"] == "unavailable"
    assert body["model_pipeline"]["status"] == "unavailable"
    assert body["rules_fallback"]["status"] == "active"
    assert unauthorized.status_code == 401
    assert other_property.status_code == 404
