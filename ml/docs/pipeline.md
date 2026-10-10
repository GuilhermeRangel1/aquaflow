# Pipeline de preparação, treinamento e inferência

O pipeline de ML do AquaFlow é um experimento reproduzível sobre dados sintéticos. Ele existe para demonstrar geração, validação, preparação, comparação temporal, registro e inferência antes de haver telemetria de hardware. Os rótulos foram criados pelo simulador; não são observações de vazamentos reais.

## Dois caminhos de preparação

O Compose e o DAG do Airflow usam os mesmos scripts, mas são execuções independentes, com saídas diferentes:

| Caminho | Como inicia | Pastas de saída |
| --- | --- | --- |
| Treinamento integrado | `docker compose up --build`, quando o artefato não existe; também pode ser forçado manualmente | Origem, relatório e preparados em `data/ml/compose/`; modelo e métricas em `data/ml/training/` |
| DAG Airflow | Habilitar e acionar `aquaflow_mock_telemetry_pipeline` em `http://localhost:8080` | Origem em `data/ml/raw/`, análise em `data/ml/analysis/` e tabelas preparadas em `data/ml/prepared/` |

O Compose não depende de o DAG ter sido acionado. O DAG termina na geração, análise e preparação; não treina o modelo. Esses arquivos e modelos locais ficam sob `data/`, ignorada pelo Git.

## Etapas do pipeline

1. **Geração:** `ml/generate_mock_data.py` cria 16 dias de horários simulados com seed fixa, cadência esperada de cinco minutos e fuso `America/Sao_Paulo`.
2. **Análise e validação:** `ml/prepare_dataset.py analyze` verifica schema, ordem e duplicidade temporal, IDs, plausibilidade de valores e coerência dos rótulos. O relatório inclui cobertura, lacunas, cenários e estatísticas.
3. **Preparação:** `ml/prepare_dataset.py prepare` exclui intervalos sem leitura e a primeira observação sem predecessor. Deriva a variação de volume e a duração real do intervalo e cria hora/dia da semana cíclicos no fuso local.
4. **Treino e seleção:** `ml/train_model.py` usa uma divisão cronológica local de oito dias de treino, quatro de validação e quatro de teste. A busca de hiperparâmetros usa validação cruzada temporal somente dentro do bloco de treino.
5. **Avaliação:** compara baseline de prevalência, regressão logística, Random Forest e HistGradientBoosting. A seleção usa average precision na validação temporal e num perfil simulado com rotina alterada. O perfil de estresse fica reservado para avaliar o modelo escolhido depois da seleção.
6. **Registro:** métricas, parâmetros e artefatos são registrados no MLflow e em arquivos locais para o notebook e o worker.
7. **Inferência:** o worker do Compose processa leituras persistidas que tenham dados suficientes para calcular as features. Registra probabilidade, hash do modelo e sinais considerados; uma previsão positiva pode criar um alerta experimental.

## Tabelas preparadas

| Arquivo | Conteúdo | Uso |
| --- | --- | --- |
| `features.csv` | Vazão, delta de volume, intervalo e codificações cíclicas de hora e dia | Entradas do classificador |
| `labels.csv` | `scenario_label` e `anomaly_label`, alinhados por `event_id` | Alvo de treino e avaliação, não feature |
| `metadata.csv` | `event_id`, timestamp UTC e série do dispositivo | Alinhamento e rastreabilidade, não feature |
| `preparation_manifest.json` | Fuso e políticas de transformação | Conferência do preparo |
| `eda_report.json` | Qualidade e estatísticas da origem | Inspeção do dataset |

O preparo não preenche lacunas com zero ou interpolação. Uma lacuna continua visível no intervalo entre observações válidas. Vazão, delta e intervalo mantêm unidades; o scaler da regressão logística é ajustado dentro do pipeline de treino. A função `ml/feature_transforms.py` mantém as transformações cíclicas compartilhadas com a inferência.

## Artefatos de treinamento e MLflow

O trainer salva em `data/ml/training/`:

- `best_model.joblib`: pipeline classificador selecionado, ajustado sem usar o bloco de teste;
- `metrics.json`: comparação, métricas de validação e teste, limitações e diagnóstico heurístico de overfitting;
- `split_manifest.json`: estratégia e limites temporais da divisão;
- `training_report.md`: síntese textual do experimento.

No Compose, MLflow persiste banco e artefatos em `data/ml/mlflow-server/` e é acessível em `http://localhost:5000`. A execução local fora do Compose usa o URI SQLite configurado pela CLI. Os relatórios não provam ausência de overfitting: dados sintéticos não estabelecem generalização para residências ou sensores reais.

Para forçar novo treino com o Compose:

```powershell
docker compose run --build --rm -e ML_RETRAIN_MODEL=true ml-trainer
docker compose restart ml-inference
```

## Notebook e gráficos

O notebook [`ml/notebooks/01_exploracao_e_avaliacao.ipynb`](../notebooks/01_exploracao_e_avaliacao.ipynb) usa o gerador e o preparador existentes. Ele cria gráficos exploratórios e, em uma seção separada, compara os candidatos e mostra a matriz de confusão, a curva precisão-recall e a curva ROC do bloco de teste usando o artefato treinado. Ele não reimplementa o treinamento. Consulte [instruções de execução e interpretação](../README.md).

## Inferência offline e worker da aplicação

`ml/predict_model.py` classifica uma série nova preparada pelo mesmo `prepare_dataset.py`. Ele consulta features e metadados, sem carregar os rótulos da série nova. Resultados e manifesto são gravados localmente em `data/ml/predictions/`.

No Compose padrão, `ml-inference` é iniciado depois da conclusão bem-sucedida do trainer. Ele consulta leituras do PostgreSQL e persiste resultados pela infraestrutura do backend. Uma leitura sem histórico/predecessor compatível, com lacuna longa ou fuso inválido pode ficar como insuficiente para inferência; isso não deve ser interpretado como previsão normal.

Previsões positivas podem abrir alertas experimentais tratáveis; previsões normais permanecem registradas sem alerta. O serviço de regras continua ativo independentemente do worker. As explicações de sinais são estimativas de sensibilidade, não atribuições causais. O hash valida a identidade do artefato, não sua validade no mundo real.

## Limites operacionais

O Airflow roda no modo `standalone`, com SQLite persistido e autenticação local desativada. Sua porta é vinculada ao loopback. O MLflow também é local. Essas opções são adequadas para a demonstração, não para uma implantação compartilhada ou de produção. Consulte [Estado atual do projeto](../../docs/estado-do-projeto.md) antes de interpretar o alcance do experimento.

As métricas, parâmetros selecionados e limitações de uma execução de referência estão em [Resultado do experimento](resultado-experimento.md). Consulte também [Métricas e parâmetros](../../docs/metricas-e-parametros.md) para os padrões e limiares que afetam a ingestão, as regras e o dashboard.
