#pragma once

// Copie este arquivo para "secrets.h" (ignorado pelo git) e preencha com valores reais.
// Nunca commite credenciais reais.

constexpr const char *WIFI_SSID = "sua-rede-wifi";
constexpr const char *WIFI_PASSWORD = "sua-senha-wifi";

// Host do broker MQTT (IP da maquina que roda o Docker Compose na LAN).
// Ex.: "192.168.0.10" em desenvolvimento. A porta e definida em include/config.h.
constexpr const char *MQTT_BROKER_HOST = "192.168.0.10";

// Credenciais de publicacao do broker (usuario aquaflow-publisher do Mosquitto).
// Correspondem a MQTT_PUBLISH_PASSWORD do docker-compose.yml. Compartilhadas e
// apenas para o prototipo local; producao exige credencial por dispositivo e TLS.
constexpr const char *MQTT_PUBLISH_USER = "aquaflow-publisher";
constexpr const char *MQTT_PUBLISH_PASSWORD = "aquaflow-local-publisher";

// Numero de serie cadastrado em POST /api/v1/devices.
constexpr const char *DEVICE_SERIAL = "ESP32-AGUA-0001";

// Chave individual do medidor, exibida uma unica vez no cadastro do dispositivo.
// Vai apenas na user property MQTT "device-key", nunca no corpo da mensagem.
constexpr const char *DEVICE_KEY = "troque-por-uma-chave-real";
