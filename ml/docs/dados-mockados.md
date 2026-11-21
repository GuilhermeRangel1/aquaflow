# Série híbrida e cenários simulados

O fluxo atual de demonstração e treinamento usa uma série híbrida: as vazões ativas são calibradas pelas medianas positivas das quatro coletas de bancada e a rotina doméstica, o calendário, as lacunas e os rótulos são simulados. Portanto, não é telemetria contínua de uma residência nem uma validação de detecção em campo.

A calibração versionada está em [`ml/collection/bench-calibration-v1.json`](../collection/bench-calibration-v1.json). Os quatro CSVs originais da bancada são versionados em `data/dados_reais/`. O pipeline lê esses arquivos, aplica as exclusões registradas e verifica que as medianas calculadas correspondem à calibração antes de gerar a série. Também é possível usar apenas o JSON de calibração para reproduzir a série sem ler os CSVs. O manifesto registra as fontes, exclusões e hipóteses da simulação.

## Gerar

Na raiz do projeto:

```powershell
python ml/build_real_dataset.py --bench-dir data/dados_reais --bench-calibration ml/collection/bench-calibration-v1.json --output data/ml/bench-household/raw/readings.csv
```

Por padrão, são gerados 16 dias, com intervalos de cinco minutos, seed 42 e fuso `America/Sao_Paulo`. O Compose, o Airflow e o notebook chamam o mesmo builder e a mesma calibração versionada. O Compose também carrega uma série gerada no PostgreSQL da conta local de Administração.

O simulador conserva os cenários de consumo normal, fluxo contínuo, consumo noturno e lacunas. Os rótulos vêm desses cenários programados; a condição da bancada não determina o rótulo. Nos fins de semana, o consumo de fundo entre 8h e 18h recebe um multiplicador de 1,2, uma hipótese adotada para a simulação. O contador acumulado avança durante lacunas, mas essas linhas não são leituras transmitidas.

## Calibração e limitações

As medianas positivas versionadas são 4,13; 4,80; 5,33 e 1,00 L/min, uma por corrida da bancada. O cálculo excluiu as oito amostras consideradas suspeitas: índices 602, 603 e 604 da corrida “direita fechada”, e 91, 92, 93, 251 e 260 da corrida “esquerda fechada”. Os CSVs são mantidos no Git para que o pipeline possa recalcular e conferir a calibração. Como os horários dos sopros restantes não são conhecidos, a mediana reduz a influência de valores extremos, mas não identifica nem remove todos os possíveis sopros.

As durações, frequência e horários dos usos, os padrões de consumo e as anomalias são simulados. O aumento de fim de semana também é uma hipótese, não uma conclusão derivada das coletas. As métricas medem o reconhecimento dos rótulos simulados e não estimam o desempenho em casas reais ou confirmam vazamentos.

## Formato e preparação

O CSV bruto contém campos de telemetria e colunas auxiliares do simulador:

| Campo | Unidade ou formato | Significado |
| --- | --- | --- |
| `device_serial` | texto | Identificador gerado para a série |
| `event_id` | texto | Identificador estável da amostra; vazio em lacunas |
| `recorded_at` | ISO 8601 UTC | Instante esperado da amostra |
| `cumulative_volume_liters` | L | Contador acumulado; vazio em lacunas |
| `flow_rate_liters_minute` | L/min | Vazão média simulada no intervalo; vazia em lacunas |
| `battery_percent` | % | Valor auxiliar simulado |
| `signal_dbm` | dBm | Valor auxiliar simulado |
| `firmware_version` | texto | Identifica a série gerada |
| `reading_present` | 0 ou 1 | Indica se houve leitura naquele instante |
| `scenario_label` | texto | Cenário simulado da amostra |
| `anomaly_label` | 0 ou 1 | Rótulo binário derivado do cenário, não diagnóstico de campo |

`prepare_dataset.py` remove horários sem leitura e deriva as features a partir das medições: vazão, variação do volume acumulado, duração real do intervalo, hora local codificada em seno e cosseno e dia da semana. Rótulos e identificadores não entram nas features.

O gerador legado [`generate_mock_data.py`](../generate_mock_data.py) ainda fornece o esqueleto temporal e os cenários ao builder; ele não é a fonte de vazões do fluxo padrão atual. Perfis `shifted` e `stress` continuam artificiais e usam a mesma calibração para avaliar mudanças simuladas de rotina, não conjuntos residenciais independentes.
