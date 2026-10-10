"""Forward authenticated MQTT v5 telemetry through the existing HTTP ingestion API."""

import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode
from pydantic import ValidationError

from app.schemas.telemetry import TelemetryInput

TOPIC_FILTER = "aquaflow/v1/devices/+/telemetry"
LOGGER = logging.getLogger(__name__)


def _device_key(properties: Properties | None) -> str | None:
    pairs = getattr(properties, "UserProperty", []) or []
    keys = [value for name, value in pairs if name == "device-key"]
    if len(keys) != 1 or not isinstance(keys[0], str):
        return None
    key = keys[0]
    return key if 0 < len(key) <= 128 and key.isascii() and key.isprintable() else None


def _forward(message: mqtt.MQTTMessage, api_url: str) -> bool:
    parts = message.topic.split("/")
    if len(parts) != 5 or parts[:3] != ["aquaflow", "v1", "devices"] or parts[4] != "telemetry":
        LOGGER.warning("MQTT topic rejected")
        return True
    serial = unquote(parts[3])
    if quote(serial, safe="") != parts[3]:
        LOGGER.warning("MQTT topic serial rejected")
        return True
    device_key = _device_key(message.properties)
    if device_key is None:
        LOGGER.warning("MQTT message missing device credential")
        return True
    try:
        telemetry = TelemetryInput.model_validate_json(message.payload)
    except ValidationError:
        LOGGER.warning("MQTT payload rejected by telemetry schema")
        return True
    if telemetry.device_serial != serial:
        LOGGER.warning("MQTT topic and payload serial disagree")
        return True

    request = Request(
        f"{api_url.rstrip('/')}/api/v1/ingestion/telemetry",
        data=message.payload,
        headers={"Content-Type": "application/json", "X-Device-Key": device_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status == 202:
                LOGGER.info("MQTT event processed: %s", telemetry.event_id)
                return True
            LOGGER.warning("MQTT event rejected with HTTP %s", response.status)
            return int(response.status) < 500
    except HTTPError as error:
        LOGGER.warning("MQTT event received HTTP %s", error.code)
        return error.code < 500
    except (OSError, URLError):
        LOGGER.warning("MQTT event delayed because the API is unavailable")
        return False


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    host = os.environ["MQTT_HOST"]
    username = os.environ["MQTT_INGEST_USER"]
    password = os.environ["MQTT_INGEST_PASSWORD"]
    api_url = os.environ["AQUAFLOW_API_URL"]
    if not password:
        raise ValueError("MQTT_INGEST_PASSWORD is required")

    while True:
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="aquaflow-ingestor",
            protocol=mqtt.MQTTv5,
            manual_ack=True,
        )
        client.username_pw_set(username, password)

        def on_connect(
            connection: mqtt.Client,
            _userdata: object,
            _flags: mqtt.ConnectFlags,
            reason_code: ReasonCode,
            _properties: Properties | None,
        ) -> None:
            if reason_code.is_failure:
                LOGGER.error("MQTT broker refused the ingestor: %s", reason_code)
                connection.disconnect()
                return
            connection.subscribe(TOPIC_FILTER, qos=1)
            LOGGER.info("MQTT ingestor subscribed")

        def on_message(
            connection: mqtt.Client, _userdata: object, message: mqtt.MQTTMessage
        ) -> None:
            if message.retain:
                LOGGER.warning("Retained MQTT telemetry ignored")
                connection.ack(message.mid, message.qos)
                return
            if _forward(message, api_url):
                connection.ack(message.mid, message.qos)
            else:
                connection.disconnect()

        client.on_connect = on_connect
        client.on_message = on_message
        session = Properties(PacketTypes.CONNECT)  # type: ignore[no-untyped-call]
        session.SessionExpiryInterval = 86400
        try:
            client.connect(
                host,
                int(os.getenv("MQTT_PORT", "1883")),
                clean_start=False,
                properties=session,
            )
            client.loop_forever(retry_first_connection=True)
        except OSError:
            LOGGER.warning("MQTT broker unavailable; retrying")
        finally:
            client.disconnect()
        time.sleep(3)


if __name__ == "__main__":
    run()
