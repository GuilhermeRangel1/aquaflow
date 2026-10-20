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

## Calibracao

O valor `FLOW_PULSES_PER_LITER` em `include/config.h` comeca em `450` (nominal do
YF-S201). O fator real varia por sensor, pressao e montagem, entao calibre com uma
medicao fisica antes de confiar no volume.

1. Deixe o firmware rodando e abra o monitor serial (`pio device monitor -b 115200`).
   Cada ciclo de envio imprime, alem de volume e vazao, a **contagem de pulsos
   acumulados** (`... N pulsos acumulados`).
2. Anote os pulsos acumulados exibidos (valor inicial).
3. Faca passar pelo sensor um **volume conhecido** (ex.: encha um recipiente de 10 L).
4. Anote os pulsos acumulados apos a passagem (valor final).
5. Calcule o fator real:

   ```
   FLOW_PULSES_PER_LITER = (pulsos_final - pulsos_inicial) / litros_passados
   ```

   Exemplo: se passaram 10 L e o contador foi de 500 para 5100, o fator e
   `(5100 - 500) / 10 = 460` pulsos por litro.
6. Atualize `FLOW_PULSES_PER_LITER` em `include/config.h`, recompile e grave
   (`pio run --target upload`). Repita com um volume maior para reduzir o erro.

> O contador de pulsos e acumulado desde o boot; um reboot zera a referencia, por
> isso sempre registre o valor inicial no comeco da medicao.

## Limitacoes conhecidas (MVP do firmware)

- O volume acumulado e contado em RAM; um reboot zera o contador local (a API ainda preserva o historico recebido).
- A fila de reenvio e em memoria e de tamanho fixo (`PENDING_QUEUE_SIZE`); reinicios descartam o que estiver pendente.
- O envio usa HTTP simples; para producao, configure `AQUAFLOW_API_BASE_URL` com HTTPS e valide o certificado da API.
- `battery_percent` nao e enviado por falta de sensor de bateria no escopo atual.
