#include "telemetry_client.h"

#include <ArduinoJson.h>
#include <WiFi.h>

namespace {

// Codifica um segmento de topico igual a quote(serial, safe="") do publicador Python:
// mantem os caracteres nao reservados (A-Z a-z 0-9 - _ . ~) e percent-encoda o resto
// como %XX em hexadecimal maiusculo. O ingestor rejeita o topico se a codificacao
// nao bater exatamente, entao esta funcao precisa espelhar o publicador.
String urlEncodeSegment(const String &value) {
    // Nao use o nome "HEX": Arduino define HEX como macro numerica (base de impressao).
    static const char kHexDigits[] = "0123456789ABCDEF";
    String encoded;
    encoded.reserve(value.length() * 3);
    for (size_t i = 0; i < value.length(); i++) {
        char c = value[i];
        bool unreserved = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                          (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' ||
                          c == '~';
        if (unreserved) {
            encoded += c;
        } else {
            encoded += '%';
            encoded += kHexDigits[(static_cast<unsigned char>(c) >> 4) & 0x0F];
            encoded += kHexDigits[static_cast<unsigned char>(c) & 0x0F];
        }
    }
    return encoded;
}

} // namespace

void TelemetryClient::begin(const char *brokerHost, int brokerPort, const char *brokerUser,
                            const char *brokerPassword, const char *deviceSerial,
                            const char *deviceKey) {
    m_deviceSerial = deviceSerial;
    m_deviceKey = deviceKey;
    m_brokerUri = String("mqtt://") + brokerHost + ":" + String(brokerPort);
    m_topic = String(MQTT_TOPIC_PREFIX) + urlEncodeSegment(m_deviceSerial) + MQTT_TOPIC_SUFFIX;

    esp_mqtt_client_config_t config = {};
    config.broker.address.uri = m_brokerUri.c_str();
    config.credentials.username = brokerUser;
    config.credentials.authentication.password = brokerPassword;
    // MQTT v5 e obrigatorio: so nele o ingestor le a user property "device-key".
    config.session.protocol_ver = MQTT_PROTOCOL_V_5;

    m_client = esp_mqtt_client_init(&config);
    if (m_client == nullptr) {
        Serial.println("Falha ao inicializar o cliente MQTT.");
        return;
    }
    esp_mqtt_client_register_event(m_client, MQTT_EVENT_ANY, TelemetryClient::handleMqttEvent, this);
    esp_mqtt_client_start(m_client);
}

void TelemetryClient::handleMqttEvent(void *handlerArgs, esp_event_base_t /*base*/,
                                      int32_t eventId, void *eventData) {
    auto *self = static_cast<TelemetryClient *>(handlerArgs);
    auto event = static_cast<esp_mqtt_event_handle_t>(eventData);
    switch (static_cast<esp_mqtt_event_id_t>(eventId)) {
        case MQTT_EVENT_CONNECTED:
            self->m_connected = true;
            Serial.println("Conectado ao broker MQTT.");
            break;
        case MQTT_EVENT_DISCONNECTED:
            self->m_connected = false;
            Serial.println("Desconectado do broker MQTT; esp-mqtt tentara reconectar.");
            break;
        case MQTT_EVENT_PUBLISHED:
            // PUBACK do QoS 1: o broker recebeu a mensagem de msg_id.
            self->m_lastAckedMsgId = event->msg_id;
            break;
        case MQTT_EVENT_ERROR:
            // A validacao de contrato/credencial e feita no servidor; aqui so sinalizamos
            // falhas de transporte. Nao registramos credenciais nem payload.
            Serial.println("Erro de transporte MQTT.");
            break;
        default:
            break;
    }
}

String TelemetryClient::buildPayload(const TelemetryReading &reading) const {
    // Mesmo schema de POST /api/v1/ingestion/telemetry. A chave NUNCA vai no corpo
    // (schema tem extra="forbid"); ela viaja apenas na user property "device-key".
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
    return body;
}

SendResult TelemetryClient::send(const TelemetryReading &reading) {
    if (m_client == nullptr || WiFi.status() != WL_CONNECTED || !m_connected) {
        return SendResult::NetworkError;
    }

    String body = buildPayload(reading);

    // User property "device-key" valida apenas para a proxima publicacao (esp-mqtt v5).
    mqtt5_user_property_handle_t userProperty = nullptr;
    esp_mqtt5_user_property_item_t items[] = {{"device-key", m_deviceKey.c_str()}};
    if (esp_mqtt5_client_set_user_property(&userProperty, items, 1) != ESP_OK) {
        return SendResult::NetworkError;
    }
    esp_mqtt5_publish_property_config_t publishProperty = {};
    publishProperty.user_property = userProperty;
    esp_err_t propertyResult = esp_mqtt5_client_set_publish_property(m_client, &publishProperty);
    if (propertyResult != ESP_OK) {
        esp_mqtt5_client_delete_user_property(userProperty);
        return SendResult::NetworkError;
    }

    m_lastAckedMsgId = 0;
    int msgId = esp_mqtt_client_publish(m_client, m_topic.c_str(), body.c_str(), body.length(),
                                        MQTT_PUBLISH_QOS, /*retain=*/0);
    // esp_mqtt5_client_set_publish_property duplica a user property internamente; liberamos
    // a nossa copia independentemente do resultado da publicacao.
    esp_mqtt5_client_delete_user_property(userProperty);

    if (msgId < 0) {
        // Fila de saida cheia ou desconectado: vai para a fila local e reenvia depois.
        return SendResult::NetworkError;
    }

    // QoS 1: esperamos o PUBACK (MQTT_EVENT_PUBLISHED) correspondente ao msgId.
    unsigned long startedAt = millis();
    while (m_lastAckedMsgId != msgId) {
        if (millis() - startedAt >= MQTT_PUBLISH_TIMEOUT_MS || !m_connected) {
            return SendResult::NetworkError;
        }
        delay(20); // cede a CPU a task do esp-mqtt, que processa o PUBACK.
    }
    return SendResult::Accepted;
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
