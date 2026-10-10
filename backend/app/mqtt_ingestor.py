"""Forward authenticated MQTT v5 telemetry through the existing HTTP ingestion API."""

import json
import logging
import os
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Literal, TypedDict
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


class IngestorStats(TypedDict):
    status: str
    messages_received: int
    messages_forwarded: int
    messages_rejected: int
    retries: int
    last_message_at: str | None


_stats_lock = Lock()
_stats: IngestorStats = {
    "status": "disconnected",
    "messages_received": 0,
    "messages_forwarded": 0,
    "messages_rejected": 0,
    "retries": 0,
    "last_message_at": None,
}


def _update_stats(*, status: str | None = None, last_message_at: str | None = None) -> None:
    with _stats_lock:
        if status is not None:
            _stats["status"] = status
        if last_message_at is not None:
            _stats["last_message_at"] = last_message_at


def _increment(
    name: Literal[
        "messages_received", "messages_forwarded", "messages_rejected", "retries"
    ],
) -> None:
    with _stats_lock:
        _stats[name] += 1


def _reject() -> bool:
    _increment("messages_rejected")
    return True


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        with _stats_lock:
            body = json.dumps(_stats).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _start_health_server() -> None:
    port = int(os.getenv("MQTT_INGESTOR_HEALTH_PORT", "8081"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    Thread(target=server.serve_forever, daemon=True).start()


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
        return _reject()
    serial = unquote(parts[3])
    if quote(serial, safe="") != parts[3]:
        LOGGER.warning("MQTT topic serial rejected")
        return _reject()
    device_key = _device_key(message.properties)
    if device_key is None:
        LOGGER.warning("MQTT message missing device credential")
        return _reject()
    try:
        telemetry = TelemetryInput.model_validate_json(message.payload)
    except ValidationError:
        LOGGER.warning("MQTT payload rejected by telemetry schema")
        return _reject()
    if telemetry.device_serial != serial:
        LOGGER.warning("MQTT topic and payload serial disagree")
        return _reject()

    request = Request(
        f"{api_url.rstrip('/')}/api/v1/ingestion/telemetry",
        data=message.payload,
        headers={"Content-Type": "application/json", "X-Device-Key": device_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status == 202:
                _increment("messages_forwarded")
                LOGGER.info("MQTT event processed: %s", telemetry.event_id)
                return True
            _increment("messages_rejected")
            LOGGER.warning("MQTT event rejected with HTTP %s", response.status)
            return int(response.status) < 500
    except HTTPError as error:
        if error.code < 500:
            _increment("messages_rejected")
        else:
            _increment("retries")
        LOGGER.warning("MQTT event received HTTP %s", error.code)
        return error.code < 500
    except (OSError, URLError):
        _increment("retries")
        LOGGER.warning("MQTT event delayed because the API is unavailable")
        return False


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _start_health_server()
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
                _update_stats(status="disconnected")
                LOGGER.error("MQTT broker refused the ingestor: %s", reason_code)
                connection.disconnect()
                return
            connection.subscribe(TOPIC_FILTER, qos=1)
            _update_stats(status="connected")
            LOGGER.info("MQTT ingestor subscribed")

        def on_disconnect(*_args: object) -> None:
            _update_stats(status="disconnected")

        def on_message(
            connection: mqtt.Client, _userdata: object, message: mqtt.MQTTMessage
        ) -> None:
            _increment("messages_received")
            _update_stats(last_message_at=datetime.now(UTC).isoformat())
            if message.retain:
                _increment("messages_rejected")
                LOGGER.warning("Retained MQTT telemetry ignored")
                connection.ack(message.mid, message.qos)
                return
            if _forward(message, api_url):
                connection.ack(message.mid, message.qos)
            else:
                connection.disconnect()

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
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
