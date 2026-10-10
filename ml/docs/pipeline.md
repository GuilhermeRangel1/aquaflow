# Pipeline de preparação e análise

O DAG `aquaflow_mock_telemetry_pipeline` está em `ml/airflow/dags/`. Ele é executado manualmente, com seed e janela fixas, em três tarefas encadeadas:

1. **Geração:** grava a entrada em `data/ml/raw/mock_readings.csv`.
2. **Análise e validação:** verifica schema, timestamps, UUIDs, valores plausíveis e rótulos; produz `data/ml/analysis/eda_report.json` com cobertura, lacunas, duplicatas, faixa temporal, contagem por cenário e estatísticas descritivas.
3. **Preparação:** produz `features.csv`, `labels.csv`, `metadata.csv` e `preparation_manifest.json` em `data/ml/prepared/`.

`features.csv` contém apenas vazão, delta do volume acumulado, duração do intervalo e codificações cíclicas de hora e dia da semana no fuso local da propriedade (`America/Sao_Paulo` por padrão). `labels.csv` mantém `scenario_label` e `anomaly_label`; `metadata.csv` guarda UUID, timestamp UTC e série para rastreabilidade. Esses metadados não entram no modelo. A primeira leitura é excluída porque não há leitura anterior para calcular o delta. As unidades permanecem explícitas; o escalonamento da regressão logística é ajustado dentro do pipeline em cada partição de treino.

Horários sem leitura não são preenchidos com zeros nem interpolados: são contados no relatório e excluídos das tabelas de observações. Uma lacuna entre duas leituras válidas permanece visível em `elapsed_minutes` e no delta acumulado. A preparação é determinística. Treinamento e inferência offline consomem os arquivos preparados pelo mesmo `prepare_dataset.py`, para manter as mesmas transformações e o mesmo fuso. A API ainda não consome o modelo.

## Experimento offline

Depois de executar o DAG, compare os candidatos com:

```powershell
docker compose --profile tools run --build --rm ml-trainer
```

A CLI usa blocos cronológicos locais de 8/4/4 dias para treino, validação e teste. Ela compara um baseline de prevalência com regressão logística, floresta aleatória e HistGradientBoosting. A busca usa amostragem aleatória reproduzível e validação cruzada temporal de três blocos apenas no período de treino. Average precision seleciona parâmetros e modelo na validação; o teste final avalia apenas o modelo selecionado e o baseline. Métricas, matrizes de confusão, manifesto do split, modelo serializado e execuções MLflow são gravados em `data/ml/training/` e `data/ml/mlflow.db`.

Esses resultados medem reconhecimento dos cenários artificiais definidos pelo gerador. Eles não estimam a precisão de detecção de vazamentos ou de consumo real.

## Inferência offline em novos dados

Após treinar, gere uma nova série simulada com seed e período diferentes, prepare-a com o mesmo comando `prepare` e execute `ml/predict_model.py` (os comandos Docker estão em [`ml/README.md`](../README.md)). O comando lê somente `features.csv`, `metadata.csv` e o manifesto da preparação; não carrega o arquivo de rótulos. Antes de inferir, confere o fuso e as features do treinamento, o alinhamento e a ordem temporal dos metadados e o SHA-256 do modelo salvo. A saída inclui uma previsão binária e uma probabilidade por leitura, além da versão do modelo e hashes dos dados no manifesto de inferência. O SHA-256 identifica o artefato local, mas ainda não substitui validação do modelo nem registro em um registry de produção.

O modo standalone e o SQLite persistido do Airflow são apenas para desenvolvimento local. O Compose padrão inicia o Airflow em `http://localhost:8080`, sem login e vinculado ao loopback da máquina. A execução Airflow e seu banco de metadados ainda precisam de uma configuração mais robusta caso o ambiente deixe de ser uma demonstração local.
