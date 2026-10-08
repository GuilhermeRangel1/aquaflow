import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient

from tests.conftest import reading_payload


@pytest.mark.asyncio
async def test_sustained_night_flow_creates_explained_alert_in_property_timezone(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    zone = ZoneInfo("America/Sao_Paulo")
    previous_day = datetime.now(UTC).astimezone(zone).date() - timedelta(days=1)
    day_start = datetime(
        previous_day.year,
        previous_day.month,
        previous_day.day,
        10,
        tzinfo=zone,
    )
    night_start = day_start.replace(hour=22)
    payloads = [
        reading_payload(
            str(uuid4()),
            (day_start + timedelta(minutes=5 * index)).isoformat(),
            cumulative_volume_liters=1000 + index * 0.25,
        )
        for index in range(7)
    ]
    payloads.extend(
        reading_payload(
            str(uuid4()),
            (night_start + timedelta(minutes=5 * index)).isoformat(),
            cumulative_volume_liters=2000 + index * 0.75,
        )
        for index in range(4)
    )

    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={"items": payloads},
    )
    alerts_response = await client.get(
        f"/api/v1/properties/{property_id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert ingestion.status_code == 200
    assert all(item["status"] == "accepted" for item in ingestion.json()["items"])
    assert alerts_response.status_code == 200
    alerts = alerts_response.json()["items"]
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["detector_type"] == "night_consumption"
    assert alert["severity"] == "medium"
    assert "horário local" in alert["reason"] or "noturno" in alert["reason"]
    assert alert["evidence"]["timezone"] == "America/Sao_Paulo"
    assert alert["evidence"]["night_window"] == "22:00-06:00"
    assert alert["evidence"]["baseline_daytime_median_liters_minute"] == pytest.approx(0.05)
    assert alert["evidence"]["minimum_increase_liters_minute"] == pytest.approx(0.1)
    assert alert["evidence"]["observed_duration_minutes"] >= 15


@pytest.mark.asyncio
async def test_offline_alert_is_opened_and_resolved_after_meter_reconnects(
    stale_meter_api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = stale_meter_api_client
    authorization = {"Authorization": f"Bearer {token}"}
    devices = await client.get("/api/v1/devices", headers=authorization)
    device_id = devices.json()["items"][0]["id"]
    health = await client.get(f"/api/v1/devices/{device_id}/health", headers=authorization)
    alerts_response = None
    for _ in range(20):
        alerts_response = await client.get(
            f"/api/v1/properties/{property_id}/alerts",
            headers=authorization,
        )
        if alerts_response.json()["items"]:
            break
        await asyncio.sleep(0.025)

    assert alerts_response is not None
    assert alerts_response.status_code == 200
    assert health.status_code == 200
    assert health.json()["connectivity"] == "offline"
    alerts = alerts_response.json()["items"]
    assert len(alerts) == 1
    offline_alert = alerts[0]
    assert offline_alert["detector_type"] == "device_offline"
    assert offline_alert["status"] == "open"
    assert offline_alert["evidence"]["expected_interval_seconds"] == 300
    assert offline_alert["evidence"]["offline_threshold_seconds"] == 600

    reconnect_payload = reading_payload(
        str(uuid4()),
        datetime.now(UTC).isoformat(),
        cumulative_volume_liters=100.0,
    )
    reconnect_payload["device_serial"] = "OFFLINE-TEST-001"
    reading = await client.post(
        "/api/v1/ingestion/telemetry",
        headers={"X-Device-Key": device_key},
        json=reconnect_payload,
    )
    refreshed_alerts = await client.get(
        f"/api/v1/properties/{property_id}/alerts",
        headers=authorization,
    )
    resolved = refreshed_alerts.json()["items"][0]

    assert reading.status_code == 202
    assert refreshed_alerts.status_code == 200
    assert resolved["id"] == offline_alert["id"]
    assert resolved["status"] == "resolved"
    assert "reconnected_at" in resolved["evidence"]


@pytest.mark.asyncio
async def test_sustained_flow_creates_explained_alert_that_owner_can_acknowledge(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=6)
    payloads = [
        reading_payload(
            str(uuid4()),
            (start + timedelta(minutes=5 * index)).isoformat(),
            flow_rate_liters_minute=0.2,
        )
        for index in range(73)
    ]

    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={"items": payloads},
    )
    assert ingestion.status_code == 200
    assert all(item["status"] == "accepted" for item in ingestion.json()["items"])

    headers = {"Authorization": f"Bearer {token}"}
    alerts_response = await client.get(
        f"/api/v1/properties/{property_id}/alerts", headers=headers
    )

    assert alerts_response.status_code == 200
    alerts = alerts_response.json()["items"]
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["status"] == "open"
    assert alert["severity"] == "high"
    assert alert["detector_type"] == "continuous_flow"
    assert alert["evidence"]["minimum_flow_rate_liters_minute"] == pytest.approx(0.1)
    assert alert["evidence"]["required_duration_minutes"] == 360
    assert alert["evidence"]["observed_flow_rate_liters_minute"] == pytest.approx(0.2)

    anomalies_response = await client.get(
        f"/api/v1/properties/{property_id}/anomalies", headers=headers
    )
    anomaly_detail = await client.get(
        f"/api/v1/anomalies/{alert['anomaly_id']}", headers=headers
    )

    assert anomalies_response.status_code == 200
    assert len(anomalies_response.json()["items"]) == 1
    assert anomaly_detail.status_code == 200
    assert anomaly_detail.json()["evidence"]["minimum_flow_rate_liters_minute"] == pytest.approx(
        0.1
    )

    acknowledged = await client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge", headers=headers
    )

    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"

    other_account = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Other Owner",
            "email": "other@example.com",
            "password": "Another-test-only-password-123!",
        },
    )
    assert other_account.status_code == 201
    other_headers = {
        "Authorization": f"Bearer {other_account.json()['tokens']['access_token']}"
    }
    hidden_alerts = await client.get(
        f"/api/v1/properties/{property_id}/alerts", headers=other_headers
    )
    hidden_action = await client.post(
        f"/api/v1/alerts/{alert['id']}/resolve", headers=other_headers
    )
    hidden_anomaly = await client.get(
        f"/api/v1/anomalies/{alert['anomaly_id']}", headers=other_headers
    )

    assert hidden_alerts.status_code == 404
    assert hidden_action.status_code == 404
    assert hidden_anomaly.status_code == 404


@pytest.mark.asyncio
async def test_flow_below_configured_minimum_does_not_create_an_alert(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=7)
    payloads = [
        reading_payload(
            str(uuid4()),
            (start + timedelta(minutes=5 * index)).isoformat(),
            flow_rate_liters_minute=0.05,
        )
        for index in range(85)
    ]

    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={"items": payloads},
    )
    assert ingestion.status_code == 200
    assert all(item["status"] == "accepted" for item in ingestion.json()["items"])

    alerts = await client.get(
        f"/api/v1/properties/{property_id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert alerts.status_code == 200
    assert alerts.json()["items"] == []


@pytest.mark.asyncio
async def test_sustained_flow_without_the_required_duration_does_not_create_an_alert(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=5, minutes=55)
    payloads = [
        reading_payload(
            str(uuid4()),
            (start + timedelta(minutes=5 * index)).isoformat(),
            flow_rate_liters_minute=0.2,
        )
        for index in range(72)
    ]

    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={"items": payloads},
    )
    assert ingestion.status_code == 200
    assert all(item["status"] == "accepted" for item in ingestion.json()["items"])

    alerts = await client.get(
        f"/api/v1/properties/{property_id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert alerts.status_code == 200
    assert alerts.json()["items"] == []


@pytest.mark.asyncio
async def test_interrupted_flow_is_not_classified_as_continuous_by_averaging_samples(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=6)
    payloads = [
        reading_payload(
            str(uuid4()),
            (start + timedelta(minutes=5 * index)).isoformat(),
            flow_rate_liters_minute=0.05 if index % 2 == 0 else 0.25,
        )
        for index in range(73)
    ]
    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={"items": payloads},
    )
    alerts = await client.get(
        f"/api/v1/properties/{property_id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert ingestion.status_code == 200
    assert all(item["status"] == "accepted" for item in ingestion.json()["items"])
    assert alerts.status_code == 200
    assert alerts.json()["items"] == []


@pytest.mark.asyncio
async def test_sustained_flow_is_detected_from_cumulative_volume_readings(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=6)
    payloads = [
        reading_payload(
            str(uuid4()),
            (start + timedelta(minutes=5 * index)).isoformat(),
            cumulative_volume_liters=float(index),
        )
        for index in range(73)
    ]

    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={"items": payloads},
    )
    assert ingestion.status_code == 200
    assert all(item["status"] == "accepted" for item in ingestion.json()["items"])

    alerts = await client.get(
        f"/api/v1/properties/{property_id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert alerts.status_code == 200
    assert len(alerts.json()["items"]) == 1
    observed = alerts.json()["items"][0]["evidence"]["observed_flow_rate_liters_minute"]
    assert observed == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_repeated_detection_is_grouped_in_the_active_alert(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=6, minutes=15)
    payloads = [
        reading_payload(
            str(uuid4()),
            (start + timedelta(minutes=5 * index)).isoformat(),
            flow_rate_liters_minute=0.2,
        )
        for index in range(76)
    ]

    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers={"X-Device-Key": device_key},
        json={"items": payloads},
    )
    assert ingestion.status_code == 200
    assert all(item["status"] == "accepted" for item in ingestion.json()["items"])

    alerts = await client.get(
        f"/api/v1/properties/{property_id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert alerts.status_code == 200
    items = alerts.json()["items"]
    assert len(items) == 1
    assert items[0]["evidence"]["occurrence_count"] == 4


@pytest.mark.asyncio
async def test_resolved_alert_allows_a_new_alert_for_a_recurrence_and_false_positive_action(
    api_client: tuple[AsyncClient, object, str, str],
) -> None:
    client, property_id, device_key, token = api_client
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=6, minutes=15)
    payloads = [
        reading_payload(
            str(uuid4()),
            (start + timedelta(minutes=5 * index)).isoformat(),
            flow_rate_liters_minute=0.2,
        )
        for index in range(73)
    ]
    device_headers = {"X-Device-Key": device_key}
    authorization = {"Authorization": f"Bearer {token}"}
    ingestion = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers=device_headers,
        json={"items": payloads},
    )
    assert ingestion.status_code == 200
    first_alert_response = await client.get(
        f"/api/v1/properties/{property_id}/alerts", headers=authorization
    )
    first_alert = first_alert_response.json()["items"][0]

    resolved = await client.post(
        f"/api/v1/alerts/{first_alert['id']}/resolve", headers=authorization
    )
    invalid_transition = await client.post(
        f"/api/v1/alerts/{first_alert['id']}/acknowledge", headers=authorization
    )
    recurrence = await client.post(
        "/api/v1/ingestion/telemetry/batch",
        headers=device_headers,
        json={
            "items": [
                reading_payload(
                    str(uuid4()),
                    (start + timedelta(minutes=5 * index)).isoformat(),
                    flow_rate_liters_minute=0.2,
                )
                for index in range(73, 76)
            ]
        },
    )
    alerts_after_recurrence = await client.get(
        f"/api/v1/properties/{property_id}/alerts", headers=authorization
    )
    all_alerts = alerts_after_recurrence.json()["items"]
    renewed_alert = next(item for item in all_alerts if item["status"] == "open")
    false_positive = await client.post(
        f"/api/v1/alerts/{renewed_alert['id']}/false-positive", headers=authorization
    )

    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert invalid_transition.status_code == 409
    assert recurrence.status_code == 200
    assert all(item["status"] == "accepted" for item in recurrence.json()["items"])
    assert len(all_alerts) == 2
    assert false_positive.status_code == 200
    assert false_positive.json()["status"] == "false_positive"
