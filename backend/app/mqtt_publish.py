"""Publish one demo reading with the MQTT v5 transport contract."""

import os
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from app.schemas.telemetry import TelemetryInput


def run() -> None:
    serial = os.environ["DEVICE_SERIAL"]
    device_key = os.environ["DEVICE_KEY"]
    if not device_key:
        raise ValueError("DEVICE_KEY is required")
    payload = TelemetryInput(
        device_serial=serial,
        event_id=os.getenv("EVENT_ID", uuid4().hex),
        recorded_at=datetime.now(UTC),
        cumulative_volume_liters=float(os.getenv("CUMULATIVE_VOLUME_LITERS", "1000")),
        firmware_version="mqtt-simulator-1",
    )
    properties = Properties(PacketTypes.PUBLISH)  # type: ignore[no-untyped-call]
    properties.UserProperty = [("device-key", device_key)]
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(os.environ["MQTT_PUBLISH_USER"], os.environ["MQTT_PUBLISH_PASSWORD"])
    client.connect(os.environ["MQTT_HOST"], int(os.getenv("MQTT_PORT", "1883")))
    client.loop_start()
    try:
        published = client.publish(
            f"aquaflow/v1/devices/{quote(serial, safe='')}/telemetry",
            payload.model_dump_json(),
            qos=1,
            retain=False,
            properties=properties,
        )
        published.wait_for_publish(timeout=10)
        if not published.is_published():
            raise RuntimeError("MQTT broker did not acknowledge the event")
        print(f"Evento publicado: {payload.event_id} ({serial})")
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    run()
