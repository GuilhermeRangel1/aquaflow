# Firmware AquaFlow (ESP32-WROOM-32)

Firmware que le um sensor de vazao por pulso, acumula volume e envia leituras para
`POST /api/v1/ingestion/telemetry`, conforme a secao 7 da [especificacao](../../especificacao-monitoramento-consumo-agua.md).
Esta e uma fatia fora do MVP atual da API/dashboard; ainda nao foi validada em hardware real.

## Pre-requisitos

- [PlatformIO](https://platformio.org/) (extensao do VS Code ou `pip install platformio`).
- Placa ESP32-WROOM-32 e um sensor de vazao por pulso (ex.: YF-S201/YF-S401) no pino definido em `include/config.h`.
- Um dispositivo ja cadastrado via `POST /devices` na API do AquaFlow, com a chave anotada (ela so e exibida uma vez).

## Configuracao

1. Copie `include/secrets.example.h` para `include/secrets.h` (arquivo ignorado pelo git).
2. Preencha `WIFI_SSID`, `WIFI_PASSWORD`, `AQUAFLOW_API_BASE_URL`, `DEVICE_SERIAL` e `DEVICE_KEY`.
3. Ajuste `FLOW_SENSOR_PIN` e `FLOW_PULSES_PER_LITER` em `include/config.h` conforme o sensor usado.

## Compilar e gravar

```powershell
cd firmware/aquaflow-esp32
pio run                 # compila
pio run --target upload # grava na placa conectada por USB
pio device monitor      # acompanha o log serial em 115200 bps
```

## Limitacoes conhecidas (MVP do firmware)

- O volume acumulado e contado em RAM; um reboot zera o contador local (a API ainda preserva o historico recebido).
- A fila de reenvio e em memoria e de tamanho fixo (`PENDING_QUEUE_SIZE`); reinicios descartam o que estiver pendente.
- O envio usa HTTP simples; para producao, configure `AQUAFLOW_API_BASE_URL` com HTTPS e valide o certificado da API.
- `battery_percent` nao e enviado por falta de sensor de bateria no escopo atual.
