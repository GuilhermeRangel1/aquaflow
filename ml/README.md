# Dados e modelos

Esta pasta concentra o trabalho de machine learning do AquaFlow. Ela contém dados mockados reproduzíveis, análise exploratória e preparação com Airflow, comparação offline de classificadores binários registrada no MLflow, uma CLI para novas séries e um worker que grava avaliações experimentais das leituras na API. No primeiro `docker compose up --build`, o Compose gera e prepara os dados e treina o modelo quando ainda não há artefato; em seguida inicia o worker. Previsões positivas criam alertas experimentais tratáveis. Os resultados usam cenários artificiais; o modelo ainda não foi validado com telemetria real.

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

Acesse [http://localhost:8080](http://localhost:8080), habilite o DAG e execute-o manualmente para repetir o pipeline Airflow. A interface local não pede login. O DAG salva a origem em `data/ml/raw/`, o relatório em `data/ml/analysis/` e as tabelas preparadas em `data/ml/prepared/`. Os arquivos não são versionados. O treinamento automático do Compose usa os mesmos scripts de geração, análise e preparação, com saídas próprias em `data/ml/compose/`, sem depender de uma execução manual do DAG.

O contêiner usa o modo `standalone` do Airflow e SQLite persistido em volume, apropriado para a demonstração local. A autenticação é desativada apenas para esta interface local, cuja porta é vinculada ao loopback. Não use essa configuração como ambiente de produção. A inicialização do Airflow pode consumir vários GB de memória.

Veja [schema, cenários e limitações](docs/dados-mockados.md) e [avaliação das fontes externas](docs/avaliacao-dataset.md).

O [contrato do pipeline](docs/pipeline.md) detalha as verificações, os arquivos de saída e as decisões para evitar imputação indevida e vazamento de rótulos.

## Comparar modelos

O Compose faz esse fluxo automaticamente quando não encontra `data/ml/training/best_model.joblib` e `metrics.json`: gera uma série sintética reproduzível, analisa e prepara os dados e compara os modelos. Enquanto o treinamento está em andamento, o worker aguarda; depois da conclusão bem-sucedida, ele inicia e processa as leituras pendentes. Se o artefato já existir, o treinamento é ignorado. Para forçar um novo treinamento, rode na raiz do projeto:

```powershell
docker compose run --build --rm -e ML_RETRAIN_MODEL=true ml-trainer
```

A CLI usa divisão cronológica local de 8/4/4 dias, faz busca aleatória reproduzível com validação cruzada temporal no bloco de treino e compara baseline de prevalência, regressão logística, floresta aleatória e HistGradientBoosting. Por padrão, também gera um perfil deslocado e outro de estresse, com rotinas, ruído e intensidades diferentes. A seleção considera a average precision média da validação temporal e do perfil deslocado; esse segundo conjunto também entra no ajuste final. O perfil de estresse fica separado até o fim e mede a resposta do modelo a mudanças não usadas na seleção. A busca usa modelos mais regularizados, como árvores rasas e folhas maiores.

O serviço MLflow é iniciado por `docker compose up --build` em [http://localhost:5000](http://localhost:5000). O treinamento automático e a execução manual de `ml-trainer` pelo Compose usam `http://mlflow:5000` para registrar parâmetros, métricas e artefatos. O servidor persiste seu banco e os artefatos em `data/ml/mlflow-server/`, separado do banco usado pelo modo local sem Compose para preservar os experimentos existentes.

O treinamento grava `metrics.json`, `split_manifest.json`, `best_model.joblib` e `training_report.md` em `data/ml/training/`, além das execuções e artefatos do MLflow em `data/ml/mlflow-server/`. O relatório compara os modelos, mostra o gap treino/CV, a variação entre folds, os resultados por perfil, matrizes de confusão e os hiperparâmetros escolhidos. O campo `overfitting_diagnostics.domain_shift_assessment` sinaliza quando o desempenho cai entre perfis. Esses sinais são diagnósticos; não existe garantia de ausência de overfitting com dados sintéticos.

## Notebook de exploração e avaliação visual

O notebook [`notebooks/01_exploracao_e_avaliacao.ipynb`](notebooks/01_exploracao_e_avaliacao.ipynb) documenta a análise e a preparação da série mockada usando as mesmas funções do pipeline (`generate_mock_data.py` e `prepare_dataset.py`). Em uma seção separada, ele visualiza a comparação dos modelos e avalia o artefato treinado na partição temporal de teste, incluindo matriz de confusão, curvas precisão-recall e ROC. As figuras são exibidas no notebook e salvas localmente em `data/ml/notebook/figures/`; esse conteúdo não é enviado ao frontend.

Para abrir e executar no VS Code, instale as dependências específicas do notebook e selecione o kernel desse ambiente:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r ml/requirements-notebook.txt
```

Inicie o projeto com `docker compose up --build` antes de executar a seção de avaliação dos modelos. Ela lê o artefato e o relatório gerados pelo treinamento do Compose e verifica que a série preparada no notebook corresponde à série usada no treino. O notebook não substitui nem retreina o pipeline automatizado. Todos os exemplos e gráficos descrevem cenários sintéticos, não vazamentos reais.

Para rodar sem Docker, instale `ml/requirements-training.txt` e execute `python ml/train_model.py` depois da preparação. Os arquivos preparados mantêm as transformações determinísticas e as unidades; o scaler da regressão logística é ajustado dentro do pipeline em cada treino. Os rótulos não entram nas features. Resultados descrevem somente o reconhecimento dos cenários simulados e não comprovam detecção no mundo real.

## Inferir em uma nova série simulada

Depois de treinar e preparar o modelo pelo fluxo acima, gere uma série com outro período e outra seed. Em seguida, use o mesmo preparador (`prepare_dataset.py`) utilizado no treinamento e rode a inferência offline:

```powershell
docker compose --profile tools run --rm ml-trainer python generate_mock_data.py --output data/ml/inference/raw/mock_readings.csv --seed 99 --start 2026-09-17T00:00:00-03:00 --timezone America/Sao_Paulo --days 4
docker compose --profile tools run --rm ml-trainer python prepare_dataset.py prepare --input data/ml/inference/raw/mock_readings.csv --output-dir data/ml/inference/prepared --timezone America/Sao_Paulo
docker compose --profile tools run --rm ml-trainer python predict_model.py
```

A CLI verifica o fuso, o conjunto de features e o hash do modelo contra o relatório de treinamento. Ela grava `data/ml/predictions/predictions.csv` com classificação, probabilidade e versão do artefato por leitura, além de `prediction_manifest.json` com hashes, contagens e limitações. A inferência não recebe os rótulos da série nova, não altera a API nem os alertas e não confirma anomalias reais. Os arquivos permanecem locais em `data/ml/`.

## Acompanhar inferências da aplicação

O worker processa leituras novas persistidas no PostgreSQL. Ele fica separado da imagem da API e é iniciado pelo Compose depois que o treinamento termina com sucesso. Para iniciar a solução completa, use:

```powershell
docker compose up --build
```

Quando o modelo já existe, o Compose reutiliza o artefato. Para treinar novamente e depois carregar o novo modelo no worker, execute o comando de retreinamento acima e reinicie o serviço com `docker compose restart ml-inference`.

Com o worker ativo, leituras válidas ainda sem avaliação são processadas uma vez por versão do modelo. Previsões positivas criam alertas experimentais de severidade média e podem ser reconhecidas, resolvidas ou marcadas como falso positivo pelo mesmo fluxo dos alertas por regras. Previsões positivas do mesmo medidor são agrupadas enquanto o alerta estiver aberto ou reconhecido. Previsões normais continuam registradas como inferências, sem criar alertas. O endpoint autenticado `GET /api/v1/properties/{property_id}/ml-inferences` lista os resultados, a versão, os dados avaliados e uma estimativa de sensibilidade dos sinais. Quando existe volume acumulado anterior, o worker deriva a vazão média do intervalo se a leitura não trouxer vazão instantânea. Se houver apenas vazão, estima a variação do volume somente quando o intervalo respeita a frequência esperada do medidor. Lacunas longas, dados insuficientes ou fuso incompatível são registrados como não avaliados. Se o worker estiver parado ou falhar, as regras do MVP continuam processando as leituras e gerando alertas.

Para conferir o fluxo completo usando o broker, a API e um PostgreSQL de teste isolado, primeiro treine o artefato atualizado como acima e depois execute:

```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test --profile ml-test run --build --rm mqtt-ml-e2e
```

O worker confere o hash e a estrutura do relatório antes de carregar o artefato local. O hash identifica o arquivo e detecta divergências; não significa que o modelo tenha sido validado para consumo real. O método explicativo substitui cada sinal isoladamente pela mediana do treino e mede como a probabilidade muda; isso é uma estimativa de sensibilidade, não uma explicação causal. Os artefatos `joblib` devem ser gerados localmente pelo próprio projeto e tratados como arquivos confiáveis.
