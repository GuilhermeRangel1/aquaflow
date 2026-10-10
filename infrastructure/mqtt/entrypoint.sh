#!/bin/sh
set -eu
umask 077

: "${MQTT_PUBLISH_PASSWORD:?MQTT_PUBLISH_PASSWORD is required}"
: "${MQTT_INGEST_PASSWORD:?MQTT_INGEST_PASSWORD is required}"

printf 'aquaflow-publisher:%s\naquaflow-ingestor:%s\n' \
  "$MQTT_PUBLISH_PASSWORD" "$MQTT_INGEST_PASSWORD" > /mosquitto/data/passwords
chmod 640 /mosquitto/data/passwords
mosquitto_passwd -U /mosquitto/data/passwords
chmod 640 /mosquitto/data/passwords
chown root:mosquitto /mosquitto/data/passwords
chown mosquitto:mosquitto /mosquitto/data

exec mosquitto -c /mosquitto/config/mosquitto.conf
