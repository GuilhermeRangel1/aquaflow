# Dados e modelos

Esta pasta concentra o experimento de machine learning do AquaFlow: séries calibradas reproduzíveis, análise e preparação, comparação offline de classificadores binários registrada no MLflow, uma CLI para novas séries e o worker integrado que avalia leituras persistidas pela aplicação. O treinamento padrão usa cenários simulados com vazão calibrada por medições físicas de bancada. As métricas não demonstram desempenho em campo.

O Compose inicia o treinamento automaticamente quando não encontra os artefatos esperados e depois inicia o worker. Cada execução manual do DAG do Airflow gera, analisa e prepara os dados, treina um candidato e registra a avaliação no MLflow. O notebook documenta a preparação e visualiza as avaliações. Veja [arquitetura](../docs/arquitetura.md), [estado atual do projeto](../docs/estado-do-projeto.md) e [pipeline detalhado](docs/pipeline.md).

O [relatório SBC](../reports/aquaflow-sbc.pdf) registra a avaliação de referência da série calibrada. Os [parâmetros e métricas do projeto](../docs/metricas-e-parametros.md) explicam os padrões usados na aplicação.

## Gerar dados simulados

Execute os comandos do Compose na raiz do repositório. Antes da primeira execução, [configure o arquivo de ambiente](../README.md#início-rápido), pois o Compose exige `DEMO_USER_PASSWORD`.

```powershell
docker compose run --build --rm ml-data-generator
```

O arquivo é criado em `data/ml/real/readings.csv`, fora do controle de versão. Para mudar seed, período ou intervalo, passe o comando completo ao serviço:

```powershell
docker compose run --build --rm ml-data-generator python build_real_dataset.py --bench-dir data/dados_reais --bench-calibration collection/bench-calibration-v1.json --seed 7 --days 16 --interval-minutes 5
```

O gerador usa apenas a biblioteca padrão do Python e também pode ser executado com `python ml/build_real_dataset.py --bench-dir data/dados_reais --bench-calibration ml/collection/bench-calibration-v1.json` na raiz do projeto. Os quatro CSVs versionados são lidos para recalcular as medianas de calibração e confirmar os mesmos parâmetros usados no experimento. Veja [schema, cenários e limitações](docs/dados-mockados.md). O conjunto Unitywater pesquisado é apenas uma referência possível de schema: **o pipeline atual não usa esse dataset**. Veja [fontes externas consideradas](docs/avaliacao-dataset.md).

## Pipeline Airflow

O DAG `aquaflow_demo_telemetry_pipeline` gera a série com seed fixa, valida o schema e a qualidade dos registros, escreve um relatório exploratório e prepara tabelas separadas para features e rótulos. O Airflow é iniciado junto com os demais serviços pelo Compose:

```powershell
docker compose up --build -d
```

Acesse [http://localhost:8080](http://localhost:8080), habilite o DAG e acione uma execução. A tarefa `train_candidate` lê as tabelas produzidas por essa execução e publica as métricas e artefatos no experimento `aquaflow-demo-airflow` do MLflow. Os arquivos ficam em `data/ml/airflow/<execução>/`, nas pastas `raw`, `analysis`, `prepared` e `training`. O log da tarefa indica o caminho da execução. O DAG guarda seu candidato separado do modelo ativo. O worker carrega o artefato inicial ou o candidato promovido pelo retreinamento da aplicação. O treinamento automático do Compose usa os mesmos scripts e roda independentemente do DAG.

As execuções por modelo recebem a tag `airflow_run_id` no MLflow para localizar o treino a partir do identificador exibido no Airflow. O contêiner usa o modo `standalone` com SQLite persistido em volume e um ambiente Python separado para as dependências do treino. A interface local tem autenticação desativada e porta vinculada ao loopback. A inicialização pode consumir vários GB de memória.

Veja [schema, cenários e limitações](docs/dados-mockados.md) e [avaliação das fontes externas](docs/avaliacao-dataset.md).

O [contrato do pipeline](docs/pipeline.md) detalha as verificações, os arquivos de saída e as decisões para evitar imputação indevida e vazamento de rótulos.

## Comparar modelos

### Simulação doméstica calibrada com a bancada

```powershell
python ml/build_real_dataset.py --bench-dir data/dados_reais --bench-calibration ml/collection/bench-calibration-v1.json --output data/ml/bench-household/raw/readings.csv
python ml/prepare_dataset.py analyze --input data/ml/bench-household/raw/readings.csv --output-dir data/ml/bench-household/analysis --timezone America/Sao_Paulo
python ml/prepare_dataset.py prepare --input data/ml/bench-household/raw/readings.csv --output-dir data/ml/bench-household/prepared --timezone America/Sao_Paulo
```

O fluxo do Compose, Airflow e retreinamento lê os quatro CSVs de `data/dados_reais/`, aplica as oito exclusões registradas e recalcula as medianas das vazões positivas. O pipeline interrompe a geração se os arquivos não corresponderem à calibração versionada. As medianas usadas continuam 4,13; 4,80; 5,33 e 1,00 L/min. Como os horários dos demais sopros são desconhecidos, a mediana reduz a influência dos extremos sem presumir que toda vazão alta foi um sopro. Os dados brutos permanecem separados das saídas geradas em `data/ml/`.

A série usa 16 dias a cada cinco minutos por padrão. Os eventos de uso duram uma fração simulada de cada intervalo, e a vazão é expressa como média desse intervalo. Nos fins de semana, das 8h às 18h, a vazão de fundo esperada aumenta 20% como hipótese da simulação. Os rótulos de fluxo contínuo, consumo noturno e lacuna vêm da agenda do simulador. As condições de bancada não são rótulos de anomalia.

O manifesto registra as fontes e as hipóteses. O Compose e o Airflow usam essa mesma calibração. As métricas desse dataset descrevem cenários simulados com vazões calibradas em bancada.

O Compose faz esse fluxo automaticamente quando não encontra `data/ml/training-bench-v2/best_model.joblib` e `metrics.json`: gera uma série calibrada reproduzível, analisa e prepara os dados e compara os modelos. Enquanto o treinamento está em andamento, o worker aguarda; depois da conclusão bem-sucedida, ele inicia e processa as leituras pendentes. Se o artefato já existir, o treinamento é ignorado. Para forçar um novo treinamento, rode na raiz do projeto:

```powershell
docker compose run --build --rm -e ML_RETRAIN_MODEL=true ml-trainer
```

A CLI usa divisão cronológica local de 8/4/4 dias, faz busca aleatória reproduzível com validação cruzada temporal no bloco de treino e compara baseline de prevalência, KNN, Árvore de Decisão e Random Forest. Por padrão, também gera um perfil deslocado e outro de estresse, com rotinas, ruído e intensidades diferentes. A seleção considera a average precision média da validação temporal e do perfil deslocado; esse segundo conjunto também entra no ajuste final. O perfil de estresse fica separado até o fim e mede a resposta do modelo a mudanças não usadas na seleção. A busca usa modelos mais regularizados, como árvores rasas e folhas maiores.

Os classificadores usam vazão, delta de volume e duração do intervalo. As colunas
de calendário continuam no contrato de entrada para compatibilidade, mas são
excluídas dentro dos pipelines para reduzir a memorização da agenda simulada.
O KNN usa votos uniformes e vizinhanças de 1% a 2,5% das amostras de cada ajuste,
com mínimo de três vizinhos quando há dados suficientes. A proporção é mantida
entre os folds e o ajuste final. As árvores têm
profundidade máxima de dois ou três níveis e folhas de pelo menos 20 ou 40 amostras.
Entre configurações próximas, a busca prefere a mais simples dentro de um erro
padrão da melhor AP. Os folds têm separação de 12 amostras.

O perfil deslocado padrão começa em agosto, antes do teste principal de setembro.
A CLI rejeita um perfil de ajuste que termine no início do teste ou depois dele.
O relatório registra os limites reais de ajuste/teste, o desempenho final dos
três modelos e diagnósticos separados de diferença treino/validação e estabilidade.
Os modelos dos candidatos e suas matrizes de treino, teste e estresse são
registrados depois da seleção. Resultados de estresse já inspecionados informam
o desenvolvimento seguinte e precisam ser complementados por novas avaliações.

O serviço MLflow é iniciado por `docker compose up --build` em [http://localhost:5000](http://localhost:5000). O treinamento automático e a execução manual de `ml-trainer` pelo Compose usam `http://mlflow:5000` para registrar parâmetros, métricas e artefatos. O servidor persiste seu banco e os artefatos em `data/ml/mlflow-server/`, separado do banco usado pelo modo local sem Compose para preservar os experimentos existentes.

O treinamento grava `metrics.json`, `split_manifest.json`, `best_model.joblib` e `training_report.md` em `data/ml/training-bench-v2/`, além das execuções e artefatos do MLflow em `data/ml/mlflow-server/`. O relatório compara os modelos, mostra o gap treino/CV, a variação entre folds, os resultados por perfil, matrizes de confusão e os hiperparâmetros escolhidos. O campo `overfitting_diagnostics.domain_shift_assessment` sinaliza quando o desempenho cai entre perfis. Esses sinais são diagnósticos; não existe garantia de ausência de overfitting com dados sintéticos.

## Notebook de exploração e avaliação visual

O notebook [`notebooks/01_ciclo_completo_de_ml_aquaflow.ipynb`](notebooks/01_ciclo_completo_de_ml_aquaflow.ipynb) começa pela exploração dos quatro CSVs físicos de bancada e documenta a análise e a preparação da série calibrada usando as mesmas funções do pipeline (`build_real_dataset.py` e `prepare_dataset.py`). Em uma seção separada, ele visualiza a comparação dos modelos e avalia o artefato treinado na partição temporal de teste, incluindo matriz de confusão, curvas precisão-recall e ROC. As figuras são exibidas no notebook e salvas localmente em `data/ml/notebook/figures/`; esse conteúdo não é enviado ao frontend.

Para abrir e executar no VS Code, instale as dependências específicas do notebook e selecione o kernel desse ambiente:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r ml/requirements-notebook.txt
```

Inicie o projeto com `docker compose up --build` antes de executar a seção de avaliação dos modelos. Ela lê o artefato e o relatório gerados pelo treinamento do Compose e verifica que a série preparada no notebook corresponde à série usada no treino. O notebook não substitui nem retreina o pipeline automatizado. Todos os exemplos e gráficos descrevem cenários sintéticos, não vazamentos reais.

Para rodar sem Docker, instale `ml/requirements-training.txt` e execute `python ml/train_model.py` depois da preparação. Os arquivos preparados mantêm as transformações determinísticas e as unidades; o scaler do KNN é ajustado dentro do pipeline em cada treino. Os rótulos não entram nas features. Resultados descrevem somente o reconhecimento dos cenários simulados e não comprovam detecção no mundo real.

## Inferir em uma nova série simulada

Depois de treinar e preparar o modelo pelo fluxo acima, gere uma série com outro período e outra seed. Em seguida, use o mesmo preparador (`prepare_dataset.py`) utilizado no treinamento e rode a inferência offline:

```powershell
docker compose --profile tools run --rm ml-trainer python build_real_dataset.py --bench-dir data/dados_reais --bench-calibration collection/bench-calibration-v1.json --output data/ml/inference/raw/household_readings.csv --seed 99 --start 2026-09-17T00:00:00-03:00 --timezone America/Sao_Paulo --days 4
docker compose --profile tools run --rm ml-trainer python prepare_dataset.py prepare --input data/ml/inference/raw/household_readings.csv --output-dir data/ml/inference/prepared --timezone America/Sao_Paulo
docker compose --profile tools run --rm ml-trainer python predict_model.py
```

A CLI verifica o fuso, o conjunto de features e o hash do modelo contra o relatório de treinamento. Ela grava `data/ml/predictions/predictions.csv` com classificação, probabilidade e versão do artefato por leitura, além de `prediction_manifest.json` com hashes, contagens e limitações. A inferência não recebe os rótulos da série nova, não altera a API nem os alertas e não confirma anomalias reais. Os arquivos permanecem locais em `data/ml/`.

## Acompanhar inferências da aplicação

Para medidores cadastrados com intervalo esperado inferior a cinco minutos, o worker agrupa as leituras em janelas fixas de cinco minutos. Isso inclui o ESP32 cadastrado com cadência de cinco segundos. O worker calcula o consumo pela diferença do contador acumulado entre os pontos finais de janelas consecutivas e divide pelo tempo observado para obter a vazão média. A inferência fica associada à última leitura válida da janela e aguarda um intervalo esperado após o fechamento. Cobertura insuficiente, lacunas, volume ausente e queda no contador deixam a janela como não avaliada. Leituras atrasadas ficam no histórico. Uma janela já avaliada não é reprocessada pela mesma versão. Medidores com cadência de cinco minutos ou mais seguem com inferência por leitura.

O worker processa leituras novas persistidas no PostgreSQL. Ele fica separado da imagem da API e é iniciado pelo Compose depois que o treinamento termina com sucesso. Para iniciar a solução completa, use:

```powershell
docker compose up --build
```

Para retreinar e promover um candidato, use **Modelos e treinamento → Treinar novamente** na conta administradora. O worker confere o artefato ativo ao processar leituras. O comando de treino do Compose atualiza o artefato inicial, usado quando não existe um candidato ativo.

O worker registra uma avaliação por leitura e versão. Previsões positivas podem abrir ou atualizar um aviso experimental do medidor. A API autenticada `GET /api/v1/properties/{property_id}/ml-inferences` expõe os resultados e atributos para as telas da propriedade. As regras determinísticas continuam funcionando sem o worker.

Para conferir o fluxo completo usando o broker, a API e um PostgreSQL de teste isolado, primeiro treine o artefato atualizado como acima e depois execute:

```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test --profile ml-test run --build --rm mqtt-ml-e2e
```

O worker confere o hash e a estrutura do relatório antes de carregar o artefato local. O hash identifica o arquivo e detecta divergências; não significa que o modelo tenha sido validado para consumo real. O método explicativo substitui cada sinal isoladamente pela mediana do treino e mede como a probabilidade muda; isso é uma estimativa de sensibilidade, não uma explicação causal. Os artefatos `joblib` devem ser gerados localmente pelo próprio projeto e tratados como arquivos confiáveis.
