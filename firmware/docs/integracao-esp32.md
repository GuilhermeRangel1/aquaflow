# Integração de um ESP32

Este guia usa a API atual do AquaFlow para enviar leituras por HTTP. O firmware ainda precisa ser adaptado ao sensor de vazão e à placa usados no protótipo; este documento não presume pinos, fator de calibração ou modelo de sensor.

## Preparar um medidor

1. Inicie a aplicação com `docker compose up` e entre no AquaFlow.
2. Abra **Medidores** e adicione um medidor de teste com um número de série exclusivo, por exemplo `ESP32-AGUA-0001`.
3. Copie a chave exibida. Ela é apresentada uma única vez; mantenha-a no dispositivo e não a publique no código ou no Git.
4. Na máquina que executa o Docker, descubra o IPv4 da rede local com `ipconfig`. O ESP32 e essa máquina precisam estar na mesma rede Wi-Fi.

Se a chave for exposta, gere outra com `POST /api/v1/devices/{device_id}/rotate-key`, autenticado como proprietário. A nova chave é exibida uma única vez e a anterior deixa de autenticar imediatamente. Consulte o ID do medidor em **Medidores** ou na resposta de `GET /api/v1/devices`.

No computador, a API fica em `http://localhost:8000`. No ESP32, `localhost` aponta para o próprio ESP32; use o IPv4 da máquina que executa o Docker, como `http://192.168.1.20:8000`. O firewall do Windows também precisa permitir a conexão na rede privada.

## Contrato de telemetria

Envie `POST /api/v1/ingestion/telemetry` com JSON e a chave no header `X-Device-Key`:

```json
{
  "device_serial": "ESP32-AGUA-0001",
  "event_id": "identificador-unico-do-evento",
  "recorded_at": "2026-10-07T15:00:00Z",
  "cumulative_volume_liters": 1000.0,
  "battery_percent": 87,
  "signal_dbm": -61,
  "firmware_version": "0.1.0"
}
```

Regras importantes para o firmware:

- Envie `recorded_at` em ISO 8601 com fuso; prefira UTC (`Z`) e sincronize o relógio por NTP.
- Envie pelo menos uma medida: `cumulative_volume_liters` ou `flow_rate_liters_minute`. O volume acumulado deve ser monotônico, exceto quando o medidor reiniciar.
- Gere um `event_id` novo por leitura e guarde o evento até obter resposta. Em retries, reutilize o mesmo ID e o mesmo conteúdo para evitar duplicidade.
- A chave do dispositivo vai no header `X-Device-Key`, nunca no JSON. Não registre a chave nos logs.
- Leituras atrasadas são aceitas dentro da janela configurada; timestamps mais de cinco minutos no futuro são rejeitados.
- O endpoint em lote é `POST /api/v1/ingestion/telemetry/batch`, com `{ "items": [...] }` e até 100 leituras por envio. Cada item retorna seu próprio resultado.

Uma leitura aceita retorna HTTP `202` com `status: "accepted"`. Um retry já gravado retorna HTTP `202` com `status: "duplicate"` e `duplicate: true`. O servidor preserva o evento bruto e atualiza a última comunicação do medidor.

Com o token de usuário, a API oferece `GET /api/v1/devices/{device_id}/health` para consultar conectividade, tempo desde a última comunicação e a leitura mais recente. O estado fica `online` até duas vezes o intervalo esperado; sem nenhuma leitura, fica `never_connected`. A rota `GET /api/v1/devices/{device_id}/readings` consulta as leituras brutas e aceita filtros `start`/`end`, `limit` e `cursor`. O proprietário também pode ajustar o nome e o intervalo esperado com `PATCH /api/v1/devices/{device_id}`.

## Testar o caminho sem firmware

O exemplo abaixo usa PowerShell e o endpoint real da API. Troque o IPv4, o número de série e a chave pelos dados do medidor que você acabou de provisionar:

```powershell
$api = "http://192.168.1.20:8000"
$deviceKey = "COLE_A_CHAVE_DO_MEDIDOR"
$serial = "ESP32-AGUA-0001"
$headers = @{ "X-Device-Key" = $deviceKey }
$timestamp = [DateTimeOffset]::UtcNow
$eventId = [guid]::NewGuid().ToString()
$body = @{
  device_serial = $serial
  event_id = $eventId
  recorded_at = $timestamp.ToString("o")
  cumulative_volume_liters = 1000.0
  firmware_version = "manual-test"
} | ConvertTo-Json

Invoke-RestMethod -Uri "$api/api/v1/ingestion/telemetry" -Method Post `
  -Headers $headers -ContentType "application/json" -Body $body

# Reenvie o mesmo evento: a resposta deve indicar duplicate = true.
Invoke-RestMethod -Uri "$api/api/v1/ingestion/telemetry" -Method Post `
  -Headers $headers -ContentType "application/json" -Body $body

# Envie uma segunda leitura com novo ID e volume acumulado maior.
Start-Sleep -Seconds 5
$nextBody = @{
  device_serial = $serial
  event_id = [guid]::NewGuid().ToString()
  recorded_at = [DateTimeOffset]::UtcNow.ToString("o")
  cumulative_volume_liters = 1000.1
  firmware_version = "manual-test"
} | ConvertTo-Json
Invoke-RestMethod -Uri "$api/api/v1/ingestion/telemetry" -Method Post `
  -Headers $headers -ContentType "application/json" -Body $nextBody
```

Depois, atualize **Medidores** para conferir a última comunicação e **Visão geral** para conferir o consumo calculado. A diferença entre as duas leituras é `0,1 L`; o retry da primeira não deve somar consumo outra vez.

## Respostas de erro comuns

- `401 invalid_device_key`: chave ausente/incorreta ou série não correspondente à chave.
- `422 invalid_request`: payload inválido, sem fuso ou sem medida de volume/vazão.
- `422 timestamp_too_far_in_future`: sincronize o relógio do ESP32.
- `422 reading_outside_accepted_window`: timestamp mais antigo que a janela de ingestão.
- Sem resposta/conexão recusada: confirme o IPv4 da máquina, a porta `8000`, a rede Wi-Fi e o firewall.

Se precisar invalidar uma chave, use a rota de rotação descrita acima. Ao retirar um medidor pela interface, a ingestão é desativada e o histórico de leituras e alertas permanece preservado.

Use HTTPS quando a API estiver fora da rede local de desenvolvimento. HTTP no Compose serve apenas para teste local.

## O que falta definir para o firmware da placa

Antes de escrever e validar um sketch específico, precisamos saber o modelo do sensor de vazão, a placa ESP32 e como o protótipo contabiliza pulsos/volume. O fator de calibração deve vir da documentação do sensor ou de uma medição física; não deve ser inventado no firmware.
