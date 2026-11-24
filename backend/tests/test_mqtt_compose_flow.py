"""End-to-end check against the Compose broker, ingestor, API and PostgreSQL."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import paho.mqtt.client as mqtt
import pytest
from httpx import AsyncClient
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties


def _publish(serial: str, device_key: str, payload: str) -> None:
    properties = Properties(PacketTypes.PUBLISH)
    properties.UserProperty = [("device-key", device_key)]
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(os.environ["MQTT_PUBLISH_USER"], os.environ["MQTT_PUBLISH_PASSWORD"])
    client.connect(os.environ["MQTT_HOST"], int(os.getenv("MQTT_PORT", "1883")))
    client.loop_start()
    try:
        info = client.publish(
            f"aquaflow/v1/devices/{serial}/telemetry",
            payload,
            qos=1,
            properties=properties,
        )
        info.wait_for_publish(timeout=10)
        assert info.is_published()
    finally:
        client.disconnect()
        client.loop_stop()


@pytest.mark.skipif(
    os.getenv("AQUAFLOW_MQTT_E2E") != "1",
    reason="requires the Compose MQTT stack",
)
@pytest.mark.asyncio
async def test_published_reading_is_visible_once_through_the_api() -> None:
    base_url = os.environ["AQUAFLOW_API_URL"]
    serial = f"MQTT-TEST-{uuid4().hex[:12]}"
    event_id = uuid4().hex
    async with AsyncClient(base_url=base_url, timeout=10) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": os.environ["DEMO_USER_EMAIL"],
                "password": os.environ["DEMO_USER_PASSWORD"],
            },
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}
        properties = await client.get("/api/v1/properties", headers=headers)
        assert properties.status_code == 200
        property_id = next(
            item["id"]
            for item in properties.json()["items"]
            if item["name"] == "Casa da Administração"
        )
        provisioned = await client.post(
            "/api/v1/devices",
            headers=headers,
            json={
                "property_id": property_id,
                "serial_number": serial,
                "name": "Teste MQTT",
                "expected_interval_seconds": 5,
            },
        )
        assert provisioned.status_code == 201
        device = provisioned.json()
        assert device["expected_interval_seconds"] == 5
        payload = json.dumps(
            {
                "device_serial": serial,
                "event_id": event_id,
                "recorded_at": datetime.now(UTC).isoformat(),
                "cumulative_volume_liters": 100.5,
            }
        )
        try:
            items: list[dict[str, object]] = []
            for attempt in range(30):
                if attempt % 5 == 0:
                    await asyncio.to_thread(_publish, serial, device["device_key"], payload)
                response = await client.get(
                    f"/api/v1/devices/{device['id']}/readings", headers=headers
                )
                assert response.status_code == 200
                items = [item for item in response.json()["items"] if item["event_id"] == event_id]
                if items:
                    break
                await asyncio.sleep(1)
            assert len(items) == 1
            assert float(items[0]["cumulative_volume_liters"]) == 100.5

            await asyncio.to_thread(_publish, serial, device["device_key"], payload)
            await asyncio.sleep(2)
            response = await client.get(f"/api/v1/devices/{device['id']}/readings", headers=headers)
            assert sum(item["event_id"] == event_id for item in response.json()["items"]) == 1
        finally:
            await client.delete(f"/api/v1/devices/{device['id']}", headers=headers)


@pytest.mark.skipif(
    os.getenv("AQUAFLOW_ML_MQTT_E2E") != "1",
    reason="requires Compose MQTT, PostgreSQL, API and a trained local model",
)
@pytest.mark.asyncio
@pytest.mark.parametrize("cadence_seconds", [300, 30, 5])
async def test_mqtt_ml_predictions_create_actionable_alerts(cadence_seconds: int) -> None:
    base_url = os.environ["AQUAFLOW_API_URL"]
    serial = f"MQTT-ML-TEST-{uuid4().hex[:12]}"
    event_ids = [uuid4().hex for _ in range(7)]
    now = datetime.now(UTC)
    # Exercise the hybrid model's daytime flow scenario at a stable local hour.
    reference_time = now.replace(hour=15, minute=25, second=0, microsecond=0)
    if reference_time > now:
        reference_time -= timedelta(days=1)
    async with AsyncClient(base_url=base_url, timeout=10) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": os.environ["DEMO_USER_EMAIL"],
                "password": os.environ["DEMO_USER_PASSWORD"],
            },
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}
        properties = await client.get("/api/v1/properties", headers=headers)
        assert properties.status_code == 200
        property_id = next(
            item["id"]
            for item in properties.json()["items"]
            if item["name"] == "Casa da Administração"
        )
        provisioned = await client.post(
            "/api/v1/devices",
            headers=headers,
            json={
                "property_id": property_id,
                "serial_number": serial,
                "name": "Teste ML MQTT",
                "expected_interval_seconds": cadence_seconds,
            },
        )
        assert provisioned.status_code == 201
        device = provisioned.json()
        payloads = []
        cumulative_volume = 100.0
        flows = [None, None, 0.0, 0.2, 0.0, 0.2, 0.2]
        sent_ids = set(event_ids)
        for index, flow in enumerate(flows):
            if cadence_seconds < 300:
                samples_per_window = 300 // cadence_seconds
                for step in range(samples_per_window):
                    cumulative_volume += 1 / samples_per_window if flow else 0
                    event_id = event_ids[index] if step == samples_per_window - 1 else uuid4().hex
                    sent_ids.add(event_id)
                    recorded_at = reference_time - timedelta(
                        minutes=45 - 5 * index, seconds=-cadence_seconds * step
                    )
                    payloads.append(
                        json.dumps(
                            {
                                "device_serial": serial,
                                "event_id": event_id,
                                "recorded_at": recorded_at.isoformat(),
                                "cumulative_volume_liters": round(cumulative_volume, 3),
                            }
                        )
                    )
                continue
            if index == 1:
                cumulative_volume += 0.2
            payload = {
                "device_serial": serial,
                "event_id": event_ids[index],
                "recorded_at": (reference_time - timedelta(minutes=40 - 5 * index)).isoformat(),
            }
            if index < 2:
                payload["cumulative_volume_liters"] = cumulative_volume
            else:
                payload["flow_rate_liters_minute"] = flow
            payloads.append(json.dumps(payload))
        try:
            for payload in payloads:
                await asyncio.to_thread(_publish, serial, device["device_key"], payload)

            expected_events = set(event_ids if cadence_seconds < 300 else event_ids[1:])
            inferences_by_event = {}
            for _attempt in range(120):
                response = await client.get(
                    f"/api/v1/properties/{property_id}/ml-inferences",
                    params={"device_id": device["id"], "limit": 100},
                    headers=headers,
                )
                assert response.status_code == 200
                inferences_by_event = {
                    item["event_id"]: item
                    for item in response.json()["items"]
                    if item["event_id"] in (sent_ids if cadence_seconds < 300 else expected_events)
                }
                if set(inferences_by_event) == expected_events:
                    break
                await asyncio.sleep(1)
            assert set(inferences_by_event) == expected_events
            if cadence_seconds < 300:
                assert inferences_by_event[event_ids[0]]["status"] == "skipped"

            cumulative_result = inferences_by_event[event_ids[1]]
            normal_result = inferences_by_event[event_ids[2]]
            exact = await client.get(
                f"/api/v1/properties/{property_id}/ml-inferences",
                params={"device_id": device["id"], "reading_id": normal_result["reading_id"]},
                headers=headers,
            )
            assert exact.status_code == 200
            assert exact.json()["items"] == [normal_result]
            selected = await client.get(
                f"/api/v1/properties/{property_id}/ml-inferences",
                params=[
                    ("device_id", device["id"]),
                    ("latest_for_reading_ids", normal_result["reading_id"]),
                    ("latest_for_reading_ids", cumulative_result["reading_id"]),
                ],
                headers=headers,
            )
            assert selected.status_code == 200
            assert {item["reading_id"] for item in selected.json()["items"]} == {
                normal_result["reading_id"],
                cumulative_result["reading_id"],
            }
            anomaly_results = [
                inferences_by_event[event_ids[5]],
                inferences_by_event[event_ids[6]],
            ]
            assert cumulative_result["status"] == "scored"
            assert cumulative_result["explanation"]["input_derivation"] == (
                "cumulative_volume_5min_window"
                if cadence_seconds < 300
                else "flow_rate_from_cumulative_volume"
            )
            assert normal_result["predicted_anomaly"] is False
            isolated = inferences_by_event[event_ids[3]]
            assert isolated["predicted_anomaly"] is True
            assert inferences_by_event[event_ids[4]]["predicted_anomaly"] is False
            for result in anomaly_results:
                assert result["status"] == "scored"
                assert result["predicted_anomaly"] is True
                assert len(result["model_version"]) == 64
                assert result["explanation"]["top_signals"]
                if cadence_seconds < 300:
                    assert result["feature_values"]["elapsed_minutes"] == 5
                    assert result["feature_values"]["volume_delta_liters"] == 1
                    assert result["feature_values"]["flow_rate_liters_minute"] == 0.2

            alerts = await client.get(
                f"/api/v1/properties/{property_id}/alerts?limit=100",
                headers=headers,
            )
            assert alerts.status_code == 200
            ml_alerts = [
                item
                for item in alerts.json()["items"]
                if item["detector_type"] == "ml_anomaly" and item["device_id"] == device["id"]
            ]
            assert len(ml_alerts) == 1
            ml_alert = ml_alerts[0]
            assert ml_alert["status"] == "open"
            assert ml_alert["severity"] == "medium"
            assert ml_alert["evidence"]["occurrence_count"] == 2
            assert isolated["id"] not in ml_alert["evidence"]["ml_inference_ids"]
            assert (
                ml_alert["evidence"]["classification_threshold"]
                == anomaly_results[-1]["explanation"]["classification_threshold"]
            )
            assert ml_alert["evidence"]["latest_ml_inference_id"] == anomaly_results[-1]["id"]
            assert ml_alert["evidence"]["model_version"] == anomaly_results[-1]["model_version"]
            summary_response = await client.get(
                f"/api/v1/devices/{device['id']}/inference-summary", headers=headers
            )
            assert summary_response.status_code == 200
            summary = summary_response.json()
            assert summary["reading_id"] == anomaly_results[-1]["reading_id"]
            assert summary["status"] == "possible_anomaly"
            analysis = summary["latest_analysis"]
            assert set(analysis) == {"reading_id", "recorded_at", "status", "alert_id"}
            assert analysis["reading_id"] == summary["reading_id"]
            assert analysis["alert_id"] == ml_alert["id"]
            recent = await client.get(
                f"/api/v1/devices/{device['id']}/recent-analysis", headers=headers
            )
            assert recent.status_code == 200
            recent_readings = recent.json()
            assert len(recent_readings) == 5
            assert recent_readings[0]["reading_id"] == summary["reading_id"]
            assert recent_readings[0]["status"] == "possible_anomaly"
            assert recent_readings[0]["alert_id"] == ml_alert["id"]
            assert "model_version" not in recent_readings[0]
            linked = await client.get(
                f"/api/v1/properties/{property_id}/alerts",
                params={"alert_id": analysis["alert_id"], "limit": 1},
                headers=headers,
            )
            assert [item["id"] for item in linked.json()["items"]] == [ml_alert["id"]]

            acknowledged = await client.post(
                f"/api/v1/alerts/{ml_alert['id']}/acknowledge", headers=headers
            )
            assert acknowledged.status_code == 200
            assert acknowledged.json()["status"] == "acknowledged"
            resolved = await client.post(
                f"/api/v1/alerts/{ml_alert['id']}/resolve", headers=headers
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "resolved"
        finally:
            await client.delete(f"/api/v1/devices/{device['id']}", headers=headers)
