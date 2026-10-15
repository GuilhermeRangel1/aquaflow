#pragma once

#include <Arduino.h>

#include "config.h"

// Uma leitura normalizada, pronta para virar o payload de POST /ingestion/telemetry.
struct TelemetryReading {
    String eventId;
    String recordedAtIso;
    float cumulativeVolumeLiters;
    float flowRateLitersMinute;
    int signalDbm;
};

// Resultado de uma tentativa de envio.
enum class SendResult {
    Accepted,
    Rejected,   // API respondeu com erro de autenticacao ou contrato; reenviar nao ajuda.
    NetworkError, // Falha de conexao/timeout; candidato a fila local.
};

// Envia leituras para a API do AquaFlow e mantem uma fila local limitada
// para leituras que falharam por problema de rede (RF04 / secao 7.1 da especificacao).
class TelemetryClient {
public:
    void begin(const char *baseUrl, const char *deviceSerial, const char *deviceKey);

    SendResult send(const TelemetryReading &reading);

    // Tenta reenviar o que estiver pendente na fila local; chame a cada iteracao do loop.
    void flushPending();

    void enqueuePending(const TelemetryReading &reading);

    size_t pendingCount() const { return m_pendingCount; }

private:
    String m_baseUrl;
    String m_deviceSerial;
    String m_deviceKey;

    TelemetryReading m_pending[PENDING_QUEUE_SIZE];
    size_t m_pendingHead = 0;
    size_t m_pendingCount = 0;
};
