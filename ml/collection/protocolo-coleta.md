# Protocolo de coleta de telemetria real (YF-S201)

O foco é o **dado real**. Este protocolo rege a coleta física que alimenta o treino do modelo de anomalia. O mock novo **deriva desta coleta**: ele empresta apenas o esqueleto temporal de [`generate_mock_data.py`](../generate_mock_data.py) (dias, cadência e agenda de cenários), mas os valores de vazão vêm sempre daqui. Não treinar com vazão puramente sintética.

Veja também [dados mockados](../docs/dados-mockados.md) e [pipeline](../docs/pipeline.md).

## Como se encaixa

1. Você coleta corridas no balde e registra cada uma em [`rotulos-template.csv`](rotulos-template.csv) — **uma linha por corrida**.
2. O **exportador** (a construir) casa cada corrida com as leituras do banco (`telemetry_readings`), pelo dispositivo e pela janela de tempo, e aplica o rótulo.
3. O **builder** (a construir) injeta essas vazões reais no esqueleto temporal do mock, gerando o CSV final de treino, que então passa por `analyze` → `prepare` → treino.

## Antes de começar (checklist de hardware)

- Fio do **sinal** (amarelo) numa **coluna isolada** da protoboard. Em repouso o nível deve ler **1** (pull-up sadio); girar o rotor deve contar pulsos e gerar vazão. Nível preso em 0 em repouso = curto entre sinal e GND — corrija antes de coletar.
- Vermelho em 5V (VIN), preto em GND. O sinal **nunca** deve passar de 3,3 V no ESP32.
- **Relógio certo.** Os horários que você anota são locais (America/Sao_Paulo); o dispositivo envia `recorded_at` em UTC (via NTP). O exportador converte, mas só funciona se os dois relógios estiverem corretos.
- (Opcional) Reduzir o intervalo de amostragem do firmware para a bancada, pra cada corrida render mais pontos (ex.: 5–10 s em vez de 30 s). Reverter depois da coleta.

## Cenários a coletar

| Cenário | O que fazer no balde | `anomaly_label` |
| --- | --- | --- |
| `normal` | Uso intermitente (abre, usa, fecha) **e** períodos totalmente parados (vazão zero). Varie vazão alta e baixa. | 0 |
| `continuous_flow` | Água correndo de forma **sustentada** por vários minutos (o "vazamento"), em intensidades diferentes. | 1 |
| `night_consumption` | Fluxo sustentado em **várias intensidades**, do fraco ao forte. De madrugada o normal é quase zero, então qualquer fluxo sustentado é suspeito: o fraco cobre gotejamento/baseline anômalo e o forte mostra vazamento noturno. | 1 |
| `missing_reading` (opcional) | Remover o fio do sinal → sem leitura. Só registrar; não gera vazão. | 1 (sem dado) |

Nota honesta: `continuous_flow` e `night_consumption` têm vazão fisicamente parecida; o que os separa é a **hora simulada** que o builder atribui (dia × madrugada). Como hora e dia da semana entram como features, o modelo aprende também o relógio, não só a água. Isso é intencional, para exercitar a regra de consumo noturno da especificação — fica registrado como suposição. Nunca afirmar que o sistema "localizou um vazamento"; usar "anomalia" ou "comportamento compatível com vazamento".

## Quantas corridas

Não há número obrigatório. ~50 baterias é só um ponto de partida — pode ser mais ou menos, conforme o tempo disponível e o quanto os dados começam a se repetir. O que importa é cobrir bem cada cenário e variar as intensidades. Proporção sugerida (ajuste à vontade):

- `normal`: a maior fatia (uso intermitente **e** períodos parados/zero; varie vazão alta e baixa, anote em `obs`).
- `continuous_flow`: bastante, variando a intensidade do fluxo.
- `night_consumption`: fluxo sustentado em **várias intensidades**, do fraco (baseline anômalo) ao forte (vazamento noturno).
- `missing_reading`: poucas, opcional.

Cada corrida deve durar o suficiente para gerar **várias leituras** — pelo menos alguns intervalos de amostragem do dispositivo.

## Como preencher a planilha

Arquivo: [`rotulos-template.csv`](rotulos-template.csv). Uma linha por corrida.

| Coluna | Formato | Significado |
| --- | --- | --- |
| `corrida` | inteiro | Número sequencial da bateria de teste (1, 2, 3, …). |
| `device_serial` | texto | Série do ESP32 usado (o `DEVICE_SERIAL` configurado no firmware). |
| `inicio_local` | `AAAA-MM-DD HH:MM` | Início da corrida, horário local (America/Sao_Paulo). Anote ao abrir a água. |
| `fim_local` | `AAAA-MM-DD HH:MM` | Fim da corrida, mesmo formato. Anote ao fechar a água. |
| `cenario` | texto | Um de: `normal`, `continuous_flow`, `night_consumption`, `missing_reading`. |
| `obs` | texto livre | Ex.: "vazão alta", "gotejamento", "torneira meio aberta". |

Exemplo (não copiar para o CSV; o template vai só com o cabeçalho):

| corrida | device_serial | inicio_local | fim_local | cenario | obs |
| --- | --- | --- | --- | --- | --- |
| 1 | AF-ESP32-001 | 2026-11-20 14:02 | 2026-11-20 14:08 | normal | uso curto, vazão média |
| 2 | AF-ESP32-001 | 2026-11-20 14:10 | 2026-11-20 14:20 | continuous_flow | fluxo sustentado forte |
| 3 | AF-ESP32-001 | 2026-11-20 14:22 | 2026-11-20 14:30 | night_consumption | fluxo fraco constante |

## Depois da coleta

Não apagar a telemetria bruta — corrigir no processamento, preservando a rastreabilidade. Com o CSV preenchido e as leituras no banco, rodamos o exportador e o builder para montar o dataset de treino real.
