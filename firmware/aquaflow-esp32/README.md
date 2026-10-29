# Firmware AquaFlow (ESP32-WROOM-32)

Firmware que le um sensor de vazao por pulso, acumula volume e **publica leituras no
broker MQTT** do AquaFlow, conforme a secao 7 da
[especificacao](../../especificacao-monitoramento-consumo-agua.md) e o
[contrato MQTT](../../docs/contrato-mqtt.md). O transporte e MQTT (requisito do
projeto); o consumidor (`mqtt_ingestor`) encaminha cada mensagem a ingestao HTTP, que
valida chave, janela temporal, idempotencia e persistencia.
Esta e uma fatia fora do MVP atual da API/dashboard; ainda nao foi validada em hardware real.

## Transporte MQTT

- Protocolo **MQTT v5** (cliente `esp-mqtt` do ESP-IDF, via `mqtt_client.h`/`mqtt5_client.h`).
  O MQTT 5 e habilitado por `sdkconfig.defaults` (`CONFIG_MQTT_PROTOCOL_5=y`) — ver "Build".
- Topico `aquaflow/v1/devices/{serial}/telemetry`, com o serial codificado em URL como
  um unico segmento (igual ao publicador de referencia).
- **QoS 1** e `retain` falso. O corpo e o mesmo JSON de
  `POST /api/v1/ingestion/telemetry` (sem campos extras: o schema usa `extra="forbid"`).
- A chave do medidor viaja **apenas** na user property MQTT v5 `device-key`, nunca no corpo.
- O firmware so observa o PUBACK do broker (recebimento). A validacao de contrato e de
  credencial acontece no servidor; mensagens invalidas sao descartadas la, com registro
  do motivo. Sem conexao ou sem PUBACK no prazo, a leitura vai para a fila local e e
  reenviada com o **mesmo** `event_id` (o ingestor deduplica por `device_id` + `event_id`).
- Credenciais e host do broker ficam em `include/secrets.h`; porta e QoS em `include/config.h`.

## Pre-requisitos

- [PlatformIO](https://platformio.org/) (extensao do VS Code ou `pip install platformio`).
- Placa ESP32-WROOM-32 e um sensor de vazao por pulso (ex.: YF-S201/YF-S401) no pino definido em `include/config.h`.
- Um dispositivo ja cadastrado via `POST /devices` na API do AquaFlow, com a chave anotada (ela so e exibida uma vez).
- O broker MQTT acessivel na rede. No prototipo local, suba o Compose e exponha a porta
  do broker (`docker compose` ja publica `1883:1883`); use o IP da maquina do Docker em
  `MQTT_BROKER_HOST`.

## Configuracao

1. Copie `include/secrets.example.h` para `include/secrets.h` (arquivo ignorado pelo git).
2. Preencha `WIFI_SSID`, `WIFI_PASSWORD`, `MQTT_BROKER_HOST`, `MQTT_PUBLISH_USER`,
   `MQTT_PUBLISH_PASSWORD`, `DEVICE_SERIAL` e `DEVICE_KEY`. As credenciais do broker
   correspondem ao usuario `aquaflow-publisher` e a `MQTT_PUBLISH_PASSWORD` do
   `docker-compose.yml`.
3. Ajuste `FLOW_SENSOR_PIN` e `FLOW_PULSES_PER_LITER` em `include/config.h` conforme o
   sensor usado. A porta do broker (`MQTT_BROKER_PORT`), o QoS e o timeout de PUBACK
   tambem ficam em `include/config.h`.

## Build (Arduino como componente do ESP-IDF)

Este firmware compila com `framework = arduino, espidf`: o Arduino entra como componente
do ESP-IDF, de modo que o `esp-mqtt` e recompilado **do fonte** honrando o
`sdkconfig.defaults`. E isso que habilita o **MQTT 5** (`CONFIG_MQTT_PROTOCOL_5=y`), cujos
simbolos `esp_mqtt5_*` nao existem na biblioteca pre-compilada do core Arduino puro.

> **A primeira compilacao e bem mais demorada**, porque o ESP-IDF e compilado do fonte
> (centenas de arquivos) e o toolchain do IDF 5.x e baixado na primeira vez. As seguintes
> sao incrementais. O layout de build (`CMakeLists.txt` na raiz e em `src/`,
> `sdkconfig.defaults`) e exigido por esse modo; os `sdkconfig.<env>` gerados sao ignorados
> pelo git, mas o `sdkconfig.defaults` e versionado.

```powershell
cd firmware/aquaflow-esp32
pio run                 # compila (primeira vez: baixa o IDF e compila do fonte; demora)
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
- A publicacao usa MQTT sem TLS (porta 1883), protegida apenas pela rede local. Para
  producao, use TLS e credencial de publicacao por dispositivo, com ACL por topico
  (ver `docs/contrato-mqtt.md`).
- `battery_percent` nao e enviado por falta de sensor de bateria no escopo atual.
