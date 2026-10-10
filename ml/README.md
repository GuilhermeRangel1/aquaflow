# Dados e modelos

Esta pasta concentra o trabalho de machine learning do AquaFlow. Ela contém dados mockados reproduzíveis, análise exploratória e preparação com Airflow, comparação offline de classificadores binários registrada no MLflow e uma CLI para inferir sobre uma nova série simulada. O experimento inicial usa rótulos de cenários artificiais; ainda não há inferência integrada à API nem modelo validado com telemetria real.

## Gerar dados simulados

Na raiz do repositório:

```powershell
docker compose run --build --rm ml-data-generator
```

O arquivo é criado em `data/mock-ml/readings.csv`, fora do controle de versão. Para mudar seed, período ou intervalo, passe o comando completo ao serviço:

```powershell
docker compose run --build --rm ml-data-generator python generate_mock_data.py --seed 7 --days 16 --interval-minutes 5
```

O gerador usa apenas a biblioteca padrão do Python e também pode ser executado com `python ml/generate_mock_data.py` na raiz do projeto. Veja [schema, cenários e limitações](docs/dados-mockados.md) e [avaliação das fontes externas](docs/avaliacao-dataset.md).

## Pipeline Airflow

O DAG `aquaflow_mock_telemetry_pipeline` gera a série com seed fixa, valida o schema e a qualidade dos registros, escreve um relatório exploratório e prepara tabelas separadas para features e rótulos. O Airflow é iniciado junto com os demais serviços pelo Compose:

```powershell
docker compose up --build -d
```

Acesse [http://localhost:8080](http://localhost:8080), habilite o DAG e execute-o manualmente. A interface local não pede login. O DAG salva a origem em `data/ml/raw/`, o relatório em `data/ml/analysis/` e as tabelas preparadas em `data/ml/prepared/`. Os arquivos não são versionados.

O contêiner usa o modo `standalone` do Airflow e SQLite persistido em volume, apropriado para a demonstração local. A autenticação é desativada apenas para esta interface local, cuja porta é vinculada ao loopback. Não use essa configuração como ambiente de produção. A inicialização do Airflow pode consumir vários GB de memória.

Veja [schema, cenários e limitações](docs/dados-mockados.md) e [avaliação das fontes externas](docs/avaliacao-dataset.md).

O [contrato do pipeline](docs/pipeline.md) detalha as verificações, os arquivos de saída e as decisões para evitar imputação indevida e vazamento de rótulos.

## Comparar modelos

Depois de habilitar e executar o DAG, rode na raiz do projeto:

```powershell
docker compose --profile tools run --build --rm ml-trainer
```

A CLI usa divisão cronológica local de 8/4/4 dias, faz busca aleatória reproduzível com validação cruzada temporal no bloco de treino e seleciona por average precision no bloco de validação. Compara baseline de prevalência, regressão logística, floresta aleatória e HistGradientBoosting. O teste final avalia somente o modelo selecionado e o baseline. Métricas, matrizes de confusão, manifesto temporal, modelo serializado e execuções do MLflow ficam em `data/ml/training/` e `data/ml/mlflow.db`.

Para rodar sem Docker, instale `ml/requirements-training.txt` e execute `python ml/train_model.py` depois da preparação. Os arquivos preparados mantêm as transformações determinísticas e as unidades; o scaler da regressão logística é ajustado dentro do pipeline em cada treino. Os rótulos não entram nas features. Resultados descrevem somente o reconhecimento dos cenários simulados e não comprovam detecção no mundo real.

## Inferir em uma nova série simulada

Depois de treinar e preparar o modelo pelo fluxo acima, gere uma série com outro período e outra seed. Em seguida, use o mesmo preparador (`prepare_dataset.py`) utilizado no treinamento e rode a inferência offline:

```powershell
docker compose --profile tools run --rm ml-trainer python generate_mock_data.py --output data/ml/inference/raw/mock_readings.csv --seed 99 --start 2026-09-17T00:00:00-03:00 --timezone America/Sao_Paulo --days 4
docker compose --profile tools run --rm ml-trainer python prepare_dataset.py prepare --input data/ml/inference/raw/mock_readings.csv --output-dir data/ml/inference/prepared --timezone America/Sao_Paulo
docker compose --profile tools run --rm ml-trainer python predict_model.py
```

A CLI verifica o fuso, o conjunto de features e o hash do modelo contra o relatório de treinamento. Ela grava `data/ml/predictions/predictions.csv` com classificação, probabilidade e versão do artefato por leitura, além de `prediction_manifest.json` com hashes, contagens e limitações. A inferência não recebe os rótulos da série nova, não altera a API nem os alertas e não confirma anomalias reais. Os arquivos permanecem locais em `data/ml/`.
