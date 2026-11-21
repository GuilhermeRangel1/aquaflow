from datetime import UTC, datetime, timedelta, tzinfo
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.models import Alert, AnomalyEvent, MLInference, TelemetryReading
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

    received_at = datetime.fromisoformat(readings.json()["items"][0]["received_at"])
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    path = f"/api/v1/devices/{device_id}/readings"
    headers = {"Authorization": f"Bearer {token}"}
    late_arrivals = await client.get(
        path,
        headers=headers,
        params={
            "window_minutes": 15,
            "received_since": (received_at - timedelta(seconds=1)).isoformat(),
        },
    )
    assert late_arrivals.status_code == 200
    assert datetime.fromisoformat(late_arrivals.json()["queried_at"]) >= received_at
    assert late_arrivals.json()["items"] == readings.json()["items"]
    no_arrivals = await client.get(
        path,
        headers=headers,
        params={"received_since": (received_at + timedelta(seconds=1)).isoformat()},
    )
    assert no_arrivals.status_code == 200
    assert no_arrivals.json()["items"] == []


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


@pytest.mark.asyncio
async def test_classification_clips_window_and_respects_false_positive(
    api_client: tuple[AsyncClient, UUID, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, property_id, device_key, token = api_client
    now = datetime.now(UTC)
    boundary = now - timedelta(days=1)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    monkeypatch.setattr("app.api.consumption.datetime", FixedClock)
    headers = {"Authorization": f"Bearer {token}"}
    for minutes, volume in ((-2, 100), (3, 110)):
        result = await client.post(
            "/api/v1/ingestion/telemetry",
            headers={"X-Device-Key": device_key},
            json=reading_payload(
                str(uuid4()),
                (boundary + timedelta(minutes=minutes)).isoformat(),
                cumulative_volume_liters=volume,
            ),
        )
        assert result.status_code == 202
    transport = client._transport
    assert isinstance(transport, ASGITransport)
    app = cast(FastAPI, transport.app)
    async with app.state.session_factory.begin() as session:
        reading = (
            await session.scalars(select(TelemetryReading).order_by(TelemetryReading.recorded_at))
        ).all()[-1]
        inference_id = uuid4()
        session.add(
            MLInference(
                id=inference_id,
                reading_id=reading.id,
                model_version="test",
                status="scored",
                predicted_anomaly=True,
                feature_values={"elapsed_minutes": 3},
                explanation={"input_derivation": "cumulative_volume_5min_window"},
                reason="Test inference",
                inferred_at=now,
            )
        )
        session.add(
            MLInference(
                reading_id=reading.id,
                model_version="older",
                status="scored",
                predicted_anomaly=False,
                feature_values={"elapsed_minutes": 3},
                explanation={"input_derivation": "cumulative_volume_5min_window"},
                reason="Older inference",
                inferred_at=now - timedelta(minutes=1),
            )
        )
        anomaly = AnomalyEvent(
            property_id=property_id,
            device_id=reading.device_id,
            detector_type="ml_anomaly",
            score=Decimal("0.9"),
            severity="medium",
            reason="Test anomaly",
            window_start=boundary,
            window_end=reading.recorded_at,
            evidence={"ml_inference_ids": [str(inference_id)]},
            detected_at=now,
        )
        session.add(anomaly)
        await session.flush()
        alert = Alert(anomaly_id=anomaly.id, status="open", created_at=now)
        session.add(alert)
        await session.flush()
        alert_id = alert.id
    path = f"/api/v1/properties/{property_id}/consumption-classification?days=1"
    assert (await client.get(path, headers=headers)).json() == {
        "normal_liters": 0,
        "flagged_liters": 6,
        "unclassified_liters": 0,
    }
    async with app.state.session_factory.begin() as session:
        stored_alert = await session.get(Alert, alert_id)
        assert stored_alert is not None
        stored_alert.status = "false_positive"
    assert (await client.get(path, headers=headers)).json() == {
        "normal_liters": 0,
        "flagged_liters": 0,
        "unclassified_liters": 6,
    }
