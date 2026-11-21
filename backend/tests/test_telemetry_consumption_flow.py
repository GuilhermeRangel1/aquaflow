from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from tests.conftest import reading_payload


@pytest.mark.asyncio
async def test_meter_description_and_monthly_consumption(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, _, device_key, token = api_client
    headers = {"Authorization": f"Bearer {token}"}
    device = (await client.get("/api/v1/devices", headers=headers)).json()["items"][0]
    path = f"/api/v1/devices/{device['id']}"
    updated = await client.patch(path, headers=headers, json={"description": "  Entrada da casa  "})
    assert updated.status_code == 200
    assert updated.json()["description"] == "Entrada da casa"
    assert (await client.get(path, headers=headers)).json()["description"] == "Entrada da casa"

    monthly = f"{path}/monthly-consumption"
    assert (await client.get(monthly)).status_code == 401
    assert (await client.get(monthly, headers=headers)).json() == {"total_volume_liters": None}
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now - start < timedelta(minutes=10):
        pytest.skip("Requires two completed sampling intervals in the calendar month")
    for at, volume in ((now - timedelta(minutes=5), 100), (now, 107)):
        saved = await client.post(
            "/api/v1/ingestion/telemetry",
            headers={"X-Device-Key": device_key},
            json=reading_payload(str(uuid4()), at.isoformat(), cumulative_volume_liters=volume),
        )
        assert saved.status_code == 202
    assert (await client.get(monthly, headers=headers)).json() == {"total_volume_liters": 7.0}
    cleared = await client.patch(path, headers=headers, json={"description": None})
    assert cleared.json()["description"] is None


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
async def test_latest_telemetry_is_the_same_in_meter_health_and_reading_history(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, _property_id, device_key, token = api_client
    measured_at = datetime.now(UTC) - timedelta(minutes=1)
    payload = reading_payload(
        str(uuid4()),
        measured_at.isoformat(),
        cumulative_volume_liters=21.5,
    )
    payload["flow_rate_liters_minute"] = 0.42
    ingested = await client.post(
        "/api/v1/ingestion/telemetry",
        json=payload,
        headers={"X-Device-Key": device_key},
    )
    device_list = await client.get("/api/v1/devices", headers={"Authorization": f"Bearer {token}"})
    device_id = device_list.json()["items"][0]["id"]
    health = await client.get(
        f"/api/v1/devices/{device_id}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    readings = await client.get(
        f"/api/v1/devices/{device_id}/readings?limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert ingested.status_code == 202
    assert health.status_code == readings.status_code == 200
    assert health.json()["latest_reading"]["id"] == readings.json()["items"][0]["id"]
    assert health.json()["latest_reading"]["event_id"] == payload["event_id"]
    assert health.json()["latest_reading"]["flow_rate_liters_minute"] == "0.420"


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
    assert summary["average_daily_volume_liters"] == pytest.approx(20.0)
    assert summary["average_hourly_volume_liters"] == pytest.approx(20.0)
    assert summary["maximum_interval_volume_liters"] == pytest.approx(20.0)
    assert summary["valid_interval_count"] == 1
    assert summary["expected_interval_count"] == 12
    assert summary["valid_data_percentage"] == pytest.approx(8.3)
    assert summary["days_with_valid_data"] == 1
    assert summary["hours_with_valid_data"] == 1
    assert datetime.fromisoformat(summary["last_reading_at"].replace("Z", "+00:00")) == (
        start + timedelta(minutes=5)
    )
    assert summary["open_alert_count"] == 0


@pytest.mark.asyncio
async def test_consumption_cursor_returns_next_bucket_without_changing_summary(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    for index in range(25):
        response = await client.post(
            "/api/v1/ingestion/telemetry",
            headers={"X-Device-Key": device_key},
            json=reading_payload(
                str(uuid4()),
                (start + timedelta(minutes=5 * index)).isoformat(),
                cumulative_volume_liters=100 + index,
            ),
        )
        assert response.status_code == 202

    params = {
        "start": start.isoformat(),
        "end": (start + timedelta(hours=2)).isoformat(),
        "granularity": "hour",
        "limit": 1,
    }
    headers = {"Authorization": f"Bearer {token}"}
    first = await client.get(
        f"/api/v1/properties/{property_id}/consumption", params=params, headers=headers
    )
    first_body = first.json()
    assert first.status_code == 200
    assert first_body["has_more"] is True
    assert first_body["cursor"]

    second = await client.get(
        f"/api/v1/properties/{property_id}/consumption",
        params={**params, "cursor": first_body["cursor"]},
        headers=headers,
    )
    second_body = second.json()
    assert second.status_code == 200
    assert second_body["items"][0]["bucket_start"] != first_body["items"][0]["bucket_start"]
    assert second_body["summary"] == first_body["summary"]


@pytest.mark.asyncio
async def test_zero_consumption_interval_is_counted_as_valid_data(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    for index in range(2):
        response = await client.post(
            "/api/v1/ingestion/telemetry",
            headers={"X-Device-Key": device_key},
            json=reading_payload(
                str(uuid4()),
                (start + timedelta(minutes=5 * index)).isoformat(),
                cumulative_volume_liters=100,
            ),
        )
        assert response.status_code == 202

    result = await client.get(
        f"/api/v1/properties/{property_id}/consumption",
        params={"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert result.status_code == 200
    assert result.json()["summary"]["valid_interval_count"] == 1
    assert result.json()["summary"]["total_volume_liters"] == 0
    assert result.json()["summary"]["valid_data_percentage"] == pytest.approx(8.3)


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
