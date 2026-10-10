# Métricas e parâmetros do AquaFlow

Este documento reúne os principais valores que afetam a ingestão, o monitoramento, a demonstração e o experimento de ML. Ele ajuda a interpretar os resultados do protótipo; não é uma recomendação de configuração para residências nem uma promessa de desempenho em produção.

Os valores estão classificados como **padrão**, **limite**, **parâmetro do experimento** ou **métrica observada**. Quando um valor for alterado no código, atualize esta tabela e aponte a fonte de verdade indicada na última coluna. Configurações por propriedade ou medidor podem substituir alguns padrões.

## Ingestão e medidores

| Parâmetro | Valor atual | Interpretação | Fonte de verdade |
| --- | --- | --- | --- |
| Fuso horário padrão da propriedade | `America/Sao_Paulo` | Aplica-se quando a propriedade não informa outro fuso válido. | [`backend/app/schemas/resources.py`](../backend/app/schemas/resources.py) |
| Intervalo esperado de leitura de um medidor novo | 300 s (5 min) | Pode ser configurado por medidor entre 30 e 86.400 s. | [`backend/app/schemas/resources.py`](../backend/app/schemas/resources.py) |
| Atraso máximo aceito para uma leitura | 7 dias | Pode ser configurado no dispositivo/propriedade, de 1 a 30 dias. | [`backend/app/core/config.py`](../backend/app/core/config.py), [`backend/app/api/telemetry.py`](../backend/app/api/telemetry.py) |
| Tolerância para relógio adiantado | 300 s (5 min) | Timestamps além dessa tolerância são rejeitados. | [`backend/app/core/config.py`](../backend/app/core/config.py) |
| Leituras por envio em lote | Até 100 | Cada item tem resultado próprio; um item inválido não converte os demais em leitura válida. | [`backend/app/schemas/telemetry.py`](../backend/app/schemas/telemetry.py) |
| Volume acumulado aceito | 0 a 1.000.000.000 L | Limite de validação do contrato HTTP. | [`backend/app/schemas/telemetry.py`](../backend/app/schemas/telemetry.py) |
| Vazão instantânea aceita | 0 a 1.000.000 L/min | Limite de validação do contrato HTTP; não é faixa calibrada de um sensor. | [`backend/app/schemas/telemetry.py`](../backend/app/schemas/telemetry.py) |
| Bateria e sinal | 0–100%; −150–0 dBm | Metadados opcionais de telemetria, não usados como features no classificador atual. | [`backend/app/schemas/telemetry.py`](../backend/app/schemas/telemetry.py), [`ml/train_model.py`](../ml/train_model.py) |

## Regras de monitoramento

| Regra | Valor atual | Como interpretar | Fonte de verdade |
| --- | --- | --- | --- |
| Fluxo contínuo | Padrão de 0,1 L/min por 360 min (6 h) | Limite e duração configuráveis por propriedade. A regra calcula vazão por leituras compatíveis e exige continuidade; lacunas maiores que dois intervalos esperados interrompem a janela. | [`backend/app/schemas/resources.py`](../backend/app/schemas/resources.py), [`backend/app/services/anomaly_detection.py`](../backend/app/services/anomaly_detection.py), [`backend/app/domain/anomalies.py`](../backend/app/domain/anomalies.py) |
| Consumo noturno | 22h–6h; aumento mínimo de 0,1 L/min; 15 min sustentados | Compara a vazão noturna com a mediana diurna válida dos últimos sete dias, no fuso local da propriedade. Requer ao menos seis intervalos diurnos válidos para formar a referência. | [`backend/app/domain/anomalies.py`](../backend/app/domain/anomalies.py), [`backend/app/services/anomaly_detection.py`](../backend/app/services/anomaly_detection.py) |
| Medidor sem comunicação | Mais de 2 intervalos esperados | Para o intervalo padrão de cinco minutos, o alerta começa após mais de dez minutos sem leitura. A verificação periódica roda a cada 60 s e o alerta ativo é resolvido quando o medidor volta a comunicar. | [`backend/app/services/device_monitor.py`](../backend/app/services/device_monitor.py) |

Esses limites são regras de monitoramento configuráveis ou decisões atuais do protótipo. Um alerta indica um comportamento a verificar; não confirma nem localiza fisicamente um vazamento.

## Dados e experimento de ML

| Parâmetro | Valor atual | Uso | Fonte de verdade |
| --- | --- | --- | --- |
| Tarefa e unidade | Classificação binária `normal/anômala`, por leitura válida com leitura anterior compatível | A primeira leitura, intervalos sem leitura e amostras sem dados necessários não viram previsões normais; são excluídos da preparação ou marcados como não avaliados, conforme o fluxo. | [`ml/prepare_dataset.py`](../ml/prepare_dataset.py), [`ml/train_model.py`](../ml/train_model.py) |
| Alvo | `anomaly_label` | Rótulo criado pelo gerador para identificar os cenários simulados. Não é confirmação de vazamento. | [`ml/generate_mock_data.py`](../ml/generate_mock_data.py) |
| Features | 7: vazão, delta de volume, duração do intervalo e seno/cosseno de hora e dia da semana locais | IDs, serial, timestamp bruto, bateria, sinal, firmware e rótulos não entram como features. | [`ml/feature_transforms.py`](../ml/feature_transforms.py), [`ml/train_model.py`](../ml/train_model.py) |
| Série padrão de treinamento | Seed 42; início em 01/09/2026; 16 dias; intervalos de 5 min; `America/Sao_Paulo` | Gera cenários reproduzíveis e registros ausentes. A série da conta demo é gerada separadamente. | [`docker-compose.yml`](../docker-compose.yml), [`ml/generate_mock_data.py`](../ml/generate_mock_data.py) |
| Perfis auxiliares | `shifted`: seed 99, início 01/10/2026; `stress`: seed 241, início 01/11/2026; ambos com 16 dias e 5 min | Séries artificiais com rotinas, ruído e intensidades diferentes. Não são dados de casas ou medidores reais. | [`ml/train_model.py`](../ml/train_model.py), [`ml/generate_mock_data.py`](../ml/generate_mock_data.py) |
| Divisão temporal principal | 8 dias de treino, 4 de validação e 4 de teste | A ordem do tempo é preservada; o bloco de teste fica fora da seleção do modelo. | [`ml/train_model.py`](../ml/train_model.py) |
| Validação cruzada e busca | 3 divisões temporais; 4 amostras de hiperparâmetros por candidato; seed 42 | Com três classificadores candidatos, a busca padrão faz 36 ajustes de validação cruzada, além dos ajustes finais e da avaliação. | [`ml/train_model.py`](../ml/train_model.py) |
| Candidatos | Regressão logística, Random Forest e HistGradientBoosting; baseline de prevalência como referência | O modelo selecionado pode mudar conforme o código e os dados gerados. A seleção usa average precision na validação temporal e no perfil `shifted`. | [`ml/train_model.py`](../ml/train_model.py) |
| Limiar de classificação | 0,5 | Uma probabilidade igual ou superior a 0,5 é classificada como positiva no pipeline atual. É um limiar técnico do experimento, não uma decisão validada para produção. | [`ml/train_model.py`](../ml/train_model.py), [`ml/inference_worker.py`](../ml/inference_worker.py) |
| Alertas de diagnóstico heurístico | gap treino/CV 0,1; desvio de AP entre folds 0,1; diferença de domínio 0,15; AP no estresse abaixo de 0,7 | São sinais para investigação de instabilidade e mudança de distribuição; não são critérios estatísticos de aprovação ou garantia de ausência de overfitting. | [`ml/train_model.py`](../ml/train_model.py) |
| Intervalo de consulta do worker ML | 5 s por padrão; mínimo efetivo 1 s | O worker consulta o banco por leituras pendentes. Não há Redis nem fila Redis neste protótipo. | [`docker-compose.yml`](../docker-compose.yml), [`ml/inference_worker.py`](../ml/inference_worker.py) |

As métricas de cada execução incluem average precision, precisão, recall, F1, acurácia balanceada e matriz de confusão. Average precision é usada na seleção porque resume a curva precisão-recall; as demais ajudam a entender os tipos de erro no limiar escolhido. A execução de referência versionada e sua interpretação estão no [relatório de resultado do experimento](../ml/docs/resultado-experimento.md).

Os números detalhados de cada execução são gravados em `data/ml/training/metrics.json` e `training_report.md`, e os experimentos ficam no MLflow local. `data/` é ignorada pelo Git; por isso, o relatório versionado registra os resultados da execução de referência, a revisão de código e os hashes usados. Uma nova execução pode produzir valores diferentes. Mesmo com hashes e métricas reproduzíveis, os resultados descrevem somente os cenários simulados.

## Atualização e leitura das métricas do dashboard

| Indicador | Janela ou intervalo | Significado | Fonte de verdade |
| --- | --- | --- | --- |
| Leituras recebidas | Últimas 24 h | Contagem associada à propriedade selecionada. | [`backend/app/api/dashboard_health.py`](../backend/app/api/dashboard_health.py) |
| Contadores MQTT | Desde que o broker iniciou | Contadores do broker compartilhado no Compose; não são contagens isoladas por propriedade. | [`backend/app/api/dashboard_health.py`](../backend/app/api/dashboard_health.py), [`docs/contrato-mqtt.md`](contrato-mqtt.md) |
| Alertas de regras | Últimas 24 h | Alertas criados pelos detectores por regras. | [`backend/app/api/dashboard_health.py`](../backend/app/api/dashboard_health.py) |
| Atualização da saúde operacional | A cada 30 s | O frontend atualiza os indicadores de API, MQTT, worker e regras. | [`frontend/src/app/dashboard/page.tsx`](../frontend/src/app/dashboard/page.tsx) |
| Atualização do consumo horário | A cada 5 min | O frontend atualiza a série horária apresentada no dashboard. | [`frontend/src/app/dashboard/page.tsx`](../frontend/src/app/dashboard/page.tsx) |

Os contadores de mensagens do broker são globais ao serviço MQTT local. Eles podem divergir das leituras da propriedade por incluírem mensagens de outros medidores, tentativas rejeitadas ou um período de execução diferente.

## Limites para interpretar resultados

- Dados da conta demo e dados do treinamento são gerados separadamente e não representam telemetria medida.
- Métricas de classificação avaliam rótulos artificiais do próprio gerador. Elas não estimam a taxa de detecção de vazamentos reais.
- Perfis `shifted` e `stress` verificam respostas a mudanças construídas pelo simulador; não substituem uma avaliação externa com dados representativos.
- As métricas não demonstram ausência de overfitting nem generalização entre casas, sensores ou rotinas.
- Parâmetros configuráveis por propriedade/medidor podem diferir dos padrões desta tabela; a evidência do alerta deve ser consultada para saber quais valores foram aplicados.
