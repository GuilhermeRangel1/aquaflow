#pragma once

// Pino digital conectado ao sinal de pulso do sensor de vazao (ex.: YF-S201/YF-S401).
constexpr int FLOW_SENSOR_PIN = 27;

// Pulsos por litro do sensor de vazao. Ajuste conforme a folha de dados do sensor usado.
constexpr float FLOW_PULSES_PER_LITER = 450.0f;

// Intervalo entre leituras enviadas a API, em milissegundos.
constexpr unsigned long SAMPLE_INTERVAL_MS = 30000;

// Tamanho da fila local usada quando o envio HTTP falha.
constexpr size_t PENDING_QUEUE_SIZE = 20;

// Timeout de cada requisicao HTTP, em milissegundos.
constexpr unsigned long HTTP_TIMEOUT_MS = 8000;

// Caminho do endpoint de ingestao, relativo a AQUAFLOW_API_BASE_URL.
constexpr const char *INGESTION_PATH = "/api/v1/ingestion/telemetry";
