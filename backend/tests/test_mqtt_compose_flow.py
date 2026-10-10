"""End-to-end check against the Compose broker, ingestor, API and PostgreSQL."""

import asyncio
import json
import os
from datetime import UTC, datetime
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
        property_id = properties.json()["items"][0]["id"]
        provisioned = await client.post(
            "/api/v1/devices",
            headers=headers,
            json={"property_id": property_id, "serial_number": serial, "name": "Teste MQTT"},
        )
        assert provisioned.status_code == 201
        device = provisioned.json()
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
