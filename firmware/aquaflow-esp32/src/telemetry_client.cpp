#include "telemetry_client.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

void TelemetryClient::begin(const char *baseUrl, const char *deviceSerial, const char *deviceKey) {
    m_baseUrl = baseUrl;
    m_deviceSerial = deviceSerial;
    m_deviceKey = deviceKey;
}

SendResult TelemetryClient::send(const TelemetryReading &reading) {
    if (WiFi.status() != WL_CONNECTED) {
        return SendResult::NetworkError;
    }

    JsonDocument doc;
    doc["device_serial"] = m_deviceSerial;
    doc["event_id"] = reading.eventId;
    doc["recorded_at"] = reading.recordedAtIso;
    doc["cumulative_volume_liters"] = reading.cumulativeVolumeLiters;
    doc["flow_rate_liters_minute"] = reading.flowRateLitersMinute;
    doc["signal_dbm"] = reading.signalDbm;
    doc["firmware_version"] = AQUAFLOW_FIRMWARE_VERSION;

    String body;
    serializeJson(doc, body);

    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);
    String url = m_baseUrl + String(INGESTION_PATH);
    if (!http.begin(url)) {
        return SendResult::NetworkError;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Key", m_deviceKey);

    int statusCode = http.POST(body);
    http.end();

    if (statusCode <= 0) {
        return SendResult::NetworkError;
    }
    if (statusCode == 202 || statusCode == 200) {
        return SendResult::Accepted;
    }
    if (statusCode >= 500) {
        return SendResult::NetworkError;
    }
    return SendResult::Rejected;
}

void TelemetryClient::enqueuePending(const TelemetryReading &reading) {
    size_t writeIndex = (m_pendingHead + m_pendingCount) % PENDING_QUEUE_SIZE;
    if (m_pendingCount == PENDING_QUEUE_SIZE) {
        // Fila cheia: descarta a leitura mais antiga para abrir espaco para a mais recente.
        m_pendingHead = (m_pendingHead + 1) % PENDING_QUEUE_SIZE;
    } else {
        m_pendingCount++;
    }
    m_pending[writeIndex] = reading;
}

void TelemetryClient::flushPending() {
    while (m_pendingCount > 0) {
        const TelemetryReading &oldest = m_pending[m_pendingHead];
        SendResult result = send(oldest);
        if (result == SendResult::NetworkError) {
            break;
        }
        m_pendingHead = (m_pendingHead + 1) % PENDING_QUEUE_SIZE;
        m_pendingCount--;
    }
}
