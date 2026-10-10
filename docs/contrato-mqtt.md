# Contrato MQTT de telemetria

O MQTT é um transporte adicional de aquisição. O consumidor encaminha cada mensagem à ingestão HTTP existente, que continua responsável por validar a chave do medidor, a janela temporal, a idempotência e a persistência no PostgreSQL. O firmware atual ainda pode usar HTTP.

## Broker local

- O Compose inicia Mosquitto 2 na rede interna, na porta 1883. A porta não é publicada no host.
- Conexões anônimas são recusadas. O usuário `aquaflow-publisher` pode publicar nos tópicos de telemetria; `aquaflow-ingestor` só pode lê-los.
- As senhas locais vêm de `MQTT_PUBLISH_PASSWORD` e `MQTT_INGEST_PASSWORD`. Os padrões do Compose servem apenas para desenvolvimento; defina valores próprios em variáveis de ambiente.
- O broker persiste sessões e mensagens pendentes no volume `aquaflow-mqtt`.

## Publicação

| Campo | Valor |
| --- | --- |
| Protocolo | MQTT v5 |
| Tópico | `aquaflow/v1/devices/{serial}/telemetry` |
| Identificador no tópico | Número de série codificado como um único segmento URL |
| QoS | 1 |
| Retain | `false` |
| Propriedade MQTT v5 | Uma `UserProperty` chamada `device-key`, com a chave individual do medidor |
| Corpo | JSON com o mesmo schema de `POST /api/v1/ingestion/telemetry` |

O campo `device_serial` do JSON deve corresponder ao serial do tópico. O corpo contém `event_id`, `recorded_at` com fuso e pelo menos `cumulative_volume_liters` ou `flow_rate_liters_minute`. As unidades são litros e litros por minuto. Metadados opcionais: `battery_percent`, `signal_dbm` e `firmware_version`. O corpo não contém a chave.

Reenvie o mesmo `event_id` e conteúdo em caso de dúvida sobre a entrega. O consumidor confirma uma mensagem QoS 1 após a API responder `202`; `accepted` e `duplicate` são ambos sucessos. Mensagens inválidas e erros HTTP 4xx são descartados com registro do motivo sem payload ou credencial. Falhas de rede ou HTTP 5xx deixam a mensagem sem confirmação para nova tentativa. A restrição única de `device_id` e `event_id` no banco evita duplicidade.

## Demonstração sem hardware

1. Inicie `docker compose up --build` e entre na conta de demonstração.
2. Em **Medidores**, crie um medidor com série exclusiva e copie a chave exibida uma única vez.
3. No PowerShell, publique uma leitura com os valores correspondentes:

```powershell
docker compose run --rm -e DEVICE_SERIAL=AF-MQTT-001 -e DEVICE_KEY=COLE_A_CHAVE -e CUMULATIVE_VOLUME_LITERS=1000 mqtt-publisher
```

4. Publique outra leitura com `CUMULATIVE_VOLUME_LITERS=1000.5`. Confira as leituras e a última comunicação em **Medidores**; a diferença aparece como consumo calculado.
5. Para conferir o percurso automaticamente em um projeto Compose isolado, com API e PostgreSQL de teste:

```powershell
docker compose -p aquaflow-mqtt-test -f docker-compose.yml -f docker-compose.test.yml --profile test run --build --rm mqtt-e2e
docker compose -p aquaflow-mqtt-test -f docker-compose.yml -f docker-compose.test.yml --profile test down --volumes
```

O teste cria um medidor no banco isolado, publica e reenvia o mesmo evento, consulta a leitura pela API e retira o medidor ao terminar. O segundo comando remove os contêineres e o volume exclusivos do teste.

## Limites atuais

O broker local usa credenciais de desenvolvimento compartilhadas para a função de publicação e TCP sem TLS, protegido pela rede interna do Compose. Para conectar ESP32 por outra rede, configurar TLS e credenciais de publicação por dispositivo, com ACL específica por tópico. A chave individual da API continua necessária em cada publicação.
