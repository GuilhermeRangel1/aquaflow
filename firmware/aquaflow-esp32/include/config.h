#pragma once

// Pino digital conectado ao sinal de pulso do sensor de vazao (ex.: YF-S201/YF-S401).
constexpr int FLOW_SENSOR_PIN = 27;

// Pulsos por litro do sensor de vazao. Ajuste conforme a folha de dados do sensor usado.
constexpr float FLOW_PULSES_PER_LITER = 450.0f;

// Intervalo entre leituras publicadas no broker, em milissegundos.
constexpr unsigned long SAMPLE_INTERVAL_MS = 30000;

// Tamanho da fila local usada quando a publicacao MQTT falha (sem conexao ou sem PUBACK).
constexpr size_t PENDING_QUEUE_SIZE = 20;

// Porta TCP do broker MQTT. 1883 e MQTT sem TLS, usado no prototipo local.
constexpr int MQTT_BROKER_PORT = 1883;

// QoS de publicacao. 1 garante PUBACK do broker (entrega ao menos uma vez).
constexpr int MQTT_PUBLISH_QOS = 1;

// Tempo maximo de espera pelo PUBACK de uma publicacao QoS 1, em milissegundos.
// Sem PUBACK dentro desse prazo a leitura vai para a fila local e e reenviada.
constexpr unsigned long MQTT_PUBLISH_TIMEOUT_MS = 10000;

// Prefixo e sufixo do topico de telemetria: aquaflow/v1/devices/{serial}/telemetry.
// O {serial} e inserido como um unico segmento, codificado em URL (ver telemetry_client).
constexpr const char *MQTT_TOPIC_PREFIX = "aquaflow/v1/devices/";
constexpr const char *MQTT_TOPIC_SUFFIX = "/telemetry";
