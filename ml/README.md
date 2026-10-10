# Dados e modelos

Esta pasta concentra o trabalho de machine learning do AquaFlow. Ela contém um gerador reproduzível de telemetria simulada, avaliação de fontes de dados e um pipeline Airflow para análise exploratória e preparação. Ainda não há pipeline de treinamento, modelo validado ou inferência em produção.

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

As lacunas previstas para o fluxo estão documentadas no manifesto e nos relatórios: leituras ausentes não são imputadas, rótulos ficam fora da tabela de features e transformações dependentes dos dados (como escala) aguardam a definição da tarefa e uma divisão temporal para evitar vazamento. O mesmo módulo de preparação deve ser usado quando treinamento e inferência forem implementados. Os detectores por regras da API permanecem disponíveis.
