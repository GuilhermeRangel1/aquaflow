#pragma once

#include <Arduino.h>

#include "mqtt_client.h"
#include "mqtt5_client.h" // API MQTT v5 (esp_mqtt5_*): user properties por publicacao.

#include "config.h"

// Uma leitura normalizada, pronta para virar o corpo JSON publicado no broker.
struct TelemetryReading {
    String eventId;
    String recordedAtIso;
    float cumulativeVolumeLiters;
    float flowRateLitersMinute;
    int signalDbm;
};

// Resultado de uma tentativa de publicacao.
//
// Por MQTT o firmware so observa se o broker recebeu a mensagem (PUBACK do QoS 1),
// nao a aceitacao final da API. A validacao de contrato e de credencial acontece no
// servidor (ingestor + API HTTP); mensagens invalidas sao descartadas la, com registro
// do motivo, sem resposta observavel aqui. Por isso nao existe um resultado "Rejected".
enum class SendResult {
    Accepted,     // Broker confirmou o recebimento (PUBACK).
    NetworkError, // Sem conexao ao broker ou sem PUBACK no prazo; candidato a fila local.
};

// Publica leituras no broker MQTT do AquaFlow (transporte exigido pelo projeto) e mantem
// uma fila local limitada para leituras que falharam por rede (RF04 / secao 7.1 da
// especificacao). O mesmo event_id e reenviado verbatim; o ingestor deduplica por
// (device_id, event_id), entao a duplicacao possivel no QoS 1 e inofensiva.
class TelemetryClient {
public:
    // Inicia o cliente esp-mqtt (MQTT v5) e dispara a conexao ao broker. A reconexao
    // ao broker e automatica (esp-mqtt); a reconexao de Wi-Fi fica no loop principal.
    void begin(const char *brokerHost, int brokerPort, const char *brokerUser,
               const char *brokerPassword, const char *deviceSerial, const char *deviceKey);

    SendResult send(const TelemetryReading &reading);

    // Tenta reenviar o que estiver pendente na fila local; chame a cada iteracao do loop.
    void flushPending();

    void enqueuePending(const TelemetryReading &reading);

    size_t pendingCount() const { return m_pendingCount; }

private:
    String buildPayload(const TelemetryReading &reading) const;

    static void handleMqttEvent(void *handlerArgs, esp_event_base_t base, int32_t eventId,
                                void *eventData);

    esp_mqtt_client_handle_t m_client = nullptr;
    String m_deviceSerial;
    String m_deviceKey;
    String m_brokerUri;
    String m_topic;

    // Estado atualizado pelo handler de eventos do esp-mqtt (roda na task do cliente).
    volatile bool m_connected = false;
    volatile int m_lastAckedMsgId = 0; // msg_id do ultimo PUBACK recebido (QoS 1 usa > 0).

    TelemetryReading m_pending[PENDING_QUEUE_SIZE];
    size_t m_pendingHead = 0;
    size_t m_pendingCount = 0;
};
