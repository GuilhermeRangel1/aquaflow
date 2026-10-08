from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import reading_payload


@pytest.mark.asyncio
async def test_cumulative_readings_are_idempotent_and_visible_as_consumption(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    headers = {"X-Device-Key": device_key}
    first = reading_payload(str(uuid4()), start.isoformat(), cumulative_volume_liters=100.0)
    second = reading_payload(
        str(uuid4()),
        (start + timedelta(minutes=5)).isoformat(),
        cumulative_volume_liters=110.0,
    )

    first_response = await client.post("/api/v1/ingestion/telemetry", json=first, headers=headers)
    second_response = await client.post("/api/v1/ingestion/telemetry", json=second, headers=headers)
    duplicate_response = await client.post(
        "/api/v1/ingestion/telemetry", json=second, headers=headers
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert second_response.json()["duplicate"] is False
    assert duplicate_response.status_code == 202
    assert duplicate_response.json()["duplicate"] is True

    consumption = await client.get(
        f"/api/v1/properties/{property_id}/consumption",
        params={
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "granularity": "hour",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert consumption.status_code == 200
    body = consumption.json()
    assert body["summary"]["total_volume_liters"] == pytest.approx(10.0)
    assert len(body["items"]) == 1
    assert body["items"][0]["volume_liters"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_consumption_summary_compares_with_the_equivalent_previous_period(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    readings = [
        (start - timedelta(minutes=5), 100.0),
        (start, 110.0),
        (start + timedelta(minutes=5), 130.0),
    ]
    for recorded_at, volume in readings:
        response = await client.post(
            "/api/v1/ingestion/telemetry",
            headers={"X-Device-Key": device_key},
            json=reading_payload(
                str(uuid4()),
                recorded_at.isoformat(),
                cumulative_volume_liters=volume,
            ),
        )
        assert response.status_code == 202

    response = await client.get(
        f"/api/v1/properties/{property_id}/consumption",
        params={
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "granularity": "hour",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["total_volume_liters"] == pytest.approx(20.0)
    assert summary["previous_period_total_volume_liters"] == pytest.approx(10.0)
    assert summary["change_volume_liters"] == pytest.approx(10.0)
    assert summary["change_percent"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_batch_keeps_valid_events_and_reports_invalid_items_individually(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, _, device_key, _ = api_client
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    response = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={
            "items": [
                reading_payload(str(uuid4()), start.isoformat(), cumulative_volume_liters=100.0),
                {
                    "device_serial": "TEST-DEVICE-001",
                    "event_id": str(uuid4()),
                    "recorded_at": start.isoformat(),
                },
                reading_payload(
                    str(uuid4()),
                    (start + timedelta(minutes=5)).isoformat(),
                    cumulative_volume_liters=101.0,
                ),
            ]
        },
    )

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["items"]] == [
        "accepted",
        "rejected",
        "accepted",
    ]


@pytest.mark.asyncio
async def test_instantaneous_flow_is_integrated_when_samples_are_close_enough(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    headers = {"X-Device-Key": device_key}
    for event_id, timestamp, rate in [
        (str(uuid4()), start, 0.2),
        (str(uuid4()), start + timedelta(minutes=5), 0.4),
    ]:
        response = await client.post(
            "/api/v1/ingestion/telemetry",
            headers=headers,
            json=reading_payload(
                event_id,
                timestamp.isoformat(),
                flow_rate_liters_minute=rate,
            ),
        )
        assert response.status_code == 202

    consumption = await client.get(
        f"/api/v1/properties/{property_id}/consumption",
        params={
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
            "granularity": "hour",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert consumption.status_code == 200
    assert consumption.json()["summary"]["total_volume_liters"] == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_ingestion_rejects_unknown_device_key(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, _, _, _ = api_client
    response = await client.post(
        "/api/v1/ingestion/telemetry",
        headers={"X-Device-Key": "not-the-device-key"},
        json=reading_payload(
            str(uuid4()),
            datetime.now(UTC).isoformat(),
            cumulative_volume_liters=100.0,
        ),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_device_key"
