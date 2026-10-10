# Dados mockados para desenvolvimento de ML

O gerador em `ml/generate_mock_data.py` produz dados sintéticos reproduzíveis. Ele serve para desenvolver e verificar o pipeline, não para estimar desempenho em vazamentos reais.

## Gerar

Na raiz do projeto:

```powershell
docker compose run --build --rm ml-data-generator python generate_mock_data.py --seed 42 --start 2026-09-01T00:00:00-03:00 --timezone America/Sao_Paulo --days 16 --interval-minutes 5
```

Também é possível executar `python ml/generate_mock_data.py` na raiz do projeto, sem instalar dependências. O caminho padrão é `data/mock-ml/readings.csv`, ignorado pelo Git. A mesma combinação de seed, início, duração e intervalo produz os mesmos bytes.

## Schema

| Coluna | Unidade ou formato | Significado |
| --- | --- | --- |
| `device_serial` | texto | Série fictícia `AF-ML-MOCK-001` |
| `event_id` | UUID | Identificador estável por seed, série e instante; vazio em lacunas |
| `recorded_at` | ISO 8601 UTC | Instante esperado da amostra |
| `cumulative_volume_liters` | L | Contador acumulado, vazio em lacunas |
| `flow_rate_liters_minute` | L/min | Vazão instantânea, vazia em lacunas |
| `battery_percent` | % | Bateria simulada, vazia em lacunas |
| `signal_dbm` | dBm | Sinal simulado, vazio em lacunas |
| `firmware_version` | texto | Versão fictícia, vazia em lacunas |
| `reading_present` | 0 ou 1 | Indica se existe leitura naquele horário |
| `scenario_label` | texto | `normal`, `continuous_flow`, `night_consumption` ou `missing_reading` |
| `anomaly_label` | 0 ou 1 | Rótulo do cenário gerado, não confirmação de vazamento |

Por padrão, a cobertura contém 16 dias locais a partir de 1º de setembro de 2026, com 4.608 horários esperados a cada cinco minutos. `recorded_at` permanece em UTC; a classificação de cenários e as horas do dia usam `America/Sao_Paulo`, fuso local padrão da propriedade. Dias alternam cenários; o consumo normal tem picos matinais, ao meio-dia e à noite, com variação pseudoaleatória determinada pela seed. Cenários de fluxo contínuo acrescentam 0,2 L/min entre 9h e 15h locais; os noturnos acrescentam 0,2 L/min entre 22h e 6h locais; os de lacuna omitem a leitura entre 12h e 14h locais. O contador continua avançando durante lacunas para representar o volume que o dispositivo mediria sem transmitir.

Linhas com `reading_present=0` descrevem horários esperados e não são payloads válidos de ingestão. Ao enviar os dados pela API/MQTT, filtre essas linhas e remova as colunas de cenário e rótulo. Na modelagem, mantenha os rótulos separados das features para evitar vazamento da resposta. A distribuição, os limiares e a ausência de falhas físicas reais são limitações deliberadas; avalie novamente os modelos quando houver telemetria do ESP32.
