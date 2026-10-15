#pragma once

// Copie este arquivo para "secrets.h" (ignorado pelo git) e preencha com valores reais.
// Nunca commite credenciais reais.

constexpr const char *WIFI_SSID = "sua-rede-wifi";
constexpr const char *WIFI_PASSWORD = "sua-senha-wifi";

// URL base da API, sem barra final. Ex.: "http://192.168.0.10:8000" em desenvolvimento
// ou "https://api.aquaflow.exemplo.com" em producao.
constexpr const char *AQUAFLOW_API_BASE_URL = "http://192.168.0.10:8000";

// Numero de serie cadastrado em POST /api/v1/devices.
constexpr const char *DEVICE_SERIAL = "ESP32-AGUA-0001";

// Chave exibida uma unica vez no cadastro do dispositivo (X-Device-Key).
constexpr const char *DEVICE_KEY = "troque-por-uma-chave-real";
