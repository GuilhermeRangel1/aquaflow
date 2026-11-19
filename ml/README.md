# Dados e modelos

Esta pasta concentra o experimento de machine learning do AquaFlow: séries híbridas reproduzíveis, análise e preparação, comparação offline de classificadores binários registrada no MLflow, uma CLI para novas séries e o worker integrado que avalia leituras persistidas pela aplicação. O treinamento padrão usa cenários simulados com vazão calibrada por medições físicas de bancada. As métricas não demonstram desempenho em campo.

O Compose inicia o treinamento automaticamente quando não encontra os artefatos esperados e depois inicia o worker. Cada execução manual do DAG do Airflow gera, analisa e prepara os dados, treina um candidato e registra a avaliação no MLflow. O notebook documenta a preparação e visualiza as avaliações. Veja [arquitetura](../docs/arquitetura.md), [estado atual do projeto](../docs/estado-do-projeto.md) e [pipeline detalhado](docs/pipeline.md).

O [relatório de resultado do experimento](docs/resultado-experimento.md) registra uma execução reproduzível do código atual, com comparação de candidatos, avaliação em perfis distintos, hashes e limitações. Os [parâmetros e métricas do projeto](../docs/metricas-e-parametros.md) explicam os padrões usados no experimento e no restante da aplicação.

## Gerar dados simulados

Na raiz do repositório:

```powershell
docker compose run --build --rm ml-data-generator
```

O arquivo é criado em `data/ml/real/readings.csv`, fora do controle de versão. Para mudar seed, período ou intervalo, passe o comando completo ao serviço:

```powershell
docker compose run --build --rm ml-data-generator python build_real_dataset.py --calibration --seed 7 --days 16 --interval-minutes 5
```

O gerador usa apenas a biblioteca padrão do Python e também pode ser executado com `python ml/build_real_dataset.py --calibration` na raiz do projeto. Veja [schema, cenários e limitações](docs/dados-mockados.md). O conjunto Unitywater pesquisado é apenas uma referência possível de schema: **o pipeline atual não usa esse dataset**. Veja [fontes externas consideradas](docs/avaliacao-dataset.md).

## Pipeline Airflow

O DAG `aquaflow_hybrid_telemetry_pipeline` gera a série com seed fixa, valida o schema e a qualidade dos registros, escreve um relatório exploratório e prepara tabelas separadas para features e rótulos. O Airflow é iniciado junto com os demais serviços pelo Compose:

```powershell
docker compose up --build -d
```

Acesse [http://localhost:8080](http://localhost:8080), habilite o DAG e acione uma execução. A tarefa `train_candidate` lê as tabelas produzidas por essa execução e publica as métricas e artefatos no experimento `aquaflow-hybrid-airflow` do MLflow. Os arquivos ficam em `data/ml/airflow/<execução>/`, nas pastas `raw`, `analysis`, `prepared` e `training`. O log da tarefa indica o caminho da execução. O worker continua lendo o modelo de inicialização em `data/ml/training-bench-v2/`. O treinamento automático do Compose usa os mesmos scripts e roda independentemente do DAG.

As execuções por modelo recebem a tag `airflow_run_id` no MLflow para localizar o treino a partir do identificador exibido no Airflow. O contêiner usa o modo `standalone` com SQLite persistido em volume e um ambiente Python separado para as dependências do treino. A interface local tem autenticação desativada e porta vinculada ao loopback. A inicialização pode consumir vários GB de memória.

Veja [schema, cenários e limitações](docs/dados-mockados.md) e [avaliação das fontes externas](docs/avaliacao-dataset.md).

O [contrato do pipeline](docs/pipeline.md) detalha as verificações, os arquivos de saída e as decisões para evitar imputação indevida e vazamento de rótulos.

## Comparar modelos

### Simulação doméstica calibrada com a bancada

```powershell
python ml/build_real_dataset.py --calibration --output data/ml/bench-household/raw/readings.csv
python ml/prepare_dataset.py analyze --input data/ml/bench-household/raw/readings.csv --output-dir data/ml/bench-household/analysis --timezone America/Sao_Paulo
python ml/prepare_dataset.py prepare --input data/ml/bench-household/raw/readings.csv --output-dir data/ml/bench-household/prepared --timezone America/Sao_Paulo
```

O modo padrão lê as medianas das vazões positivas das quatro corridas da calibração versionada. As oito leituras suspeitas, incluindo o pico de 49,6 L/min, foram excluídas antes do cálculo. Como os horários dos demais sopros são desconhecidos, a mediana reduz a influência dos extremos sem presumir que toda vazão alta foi um sopro. Os arquivos originais permanecem separados.

A série usa 16 dias a cada cinco minutos por padrão. Os eventos de uso duram uma fração simulada de cada intervalo, e a vazão é expressa como média desse intervalo. Nos fins de semana, das 8h às 18h, a vazão de fundo esperada aumenta 20% como hipótese da simulação. Os rótulos de fluxo contínuo, consumo noturno e lacuna vêm da agenda do simulador. As condições de bancada não são rótulos de anomalia.

O manifesto registra as fontes e as hipóteses. O Compose e o Airflow usam essa mesma calibração. As métricas desse dataset descrevem cenários simulados com vazões calibradas em bancada.

O Compose faz esse fluxo automaticamente quando não encontra `data/ml/training-bench-v2/best_model.joblib` e `metrics.json`: gera uma série híbrida reproduzível, analisa e prepara os dados e compara os modelos. Enquanto o treinamento está em andamento, o worker aguarda; depois da conclusão bem-sucedida, ele inicia e processa as leituras pendentes. Se o artefato já existir, o treinamento é ignorado. Para forçar um novo treinamento, rode na raiz do projeto:

```powershell
docker compose run --build --rm -e ML_RETRAIN_MODEL=true ml-trainer
```

A CLI usa divisão cronológica local de 8/4/4 dias, faz busca aleatória reproduzível com validação cruzada temporal no bloco de treino e compara baseline de prevalência, KNN, Árvore de Decisão e Random Forest. Por padrão, também gera um perfil deslocado e outro de estresse, com rotinas, ruído e intensidades diferentes. A seleção considera a average precision média da validação temporal e do perfil deslocado; esse segundo conjunto também entra no ajuste final. O perfil de estresse fica separado até o fim e mede a resposta do modelo a mudanças não usadas na seleção. A busca usa modelos mais regularizados, como árvores rasas e folhas maiores.

O serviço MLflow é iniciado por `docker compose up --build` em [http://localhost:5000](http://localhost:5000). O treinamento automático e a execução manual de `ml-trainer` pelo Compose usam `http://mlflow:5000` para registrar parâmetros, métricas e artefatos. O servidor persiste seu banco e os artefatos em `data/ml/mlflow-server/`, separado do banco usado pelo modo local sem Compose para preservar os experimentos existentes.

O treinamento grava `metrics.json`, `split_manifest.json`, `best_model.joblib` e `training_report.md` em `data/ml/training-bench-v2/`, além das execuções e artefatos do MLflow em `data/ml/mlflow-server/`. O relatório compara os modelos, mostra o gap treino/CV, a variação entre folds, os resultados por perfil, matrizes de confusão e os hiperparâmetros escolhidos. O campo `overfitting_diagnostics.domain_shift_assessment` sinaliza quando o desempenho cai entre perfis. Esses sinais são diagnósticos; não existe garantia de ausência de overfitting com dados sintéticos.

## Notebook de exploração e avaliação visual

O notebook [`notebooks/01_exploracao_e_avaliacao.ipynb`](notebooks/01_exploracao_e_avaliacao.ipynb) documenta a análise e a preparação da série híbrida usando as mesmas funções do pipeline (`build_real_dataset.py` e `prepare_dataset.py`). Em uma seção separada, ele visualiza a comparação dos modelos e avalia o artefato treinado na partição temporal de teste, incluindo matriz de confusão, curvas precisão-recall e ROC. As figuras são exibidas no notebook e salvas localmente em `data/ml/notebook/figures/`; esse conteúdo não é enviado ao frontend.

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
docker compose --profile tools run --rm ml-trainer python build_real_dataset.py --calibration --output data/ml/inference/raw/household_readings.csv --seed 99 --start 2026-09-17T00:00:00-03:00 --timezone America/Sao_Paulo --days 4
docker compose --profile tools run --rm ml-trainer python prepare_dataset.py prepare --input data/ml/inference/raw/household_readings.csv --output-dir data/ml/inference/prepared --timezone America/Sao_Paulo
docker compose --profile tools run --rm ml-trainer python predict_model.py
```

A CLI verifica o fuso, o conjunto de features e o hash do modelo contra o relatório de treinamento. Ela grava `data/ml/predictions/predictions.csv` com classificação, probabilidade e versão do artefato por leitura, além de `prediction_manifest.json` com hashes, contagens e limitações. A inferência não recebe os rótulos da série nova, não altera a API nem os alertas e não confirma anomalias reais. Os arquivos permanecem locais em `data/ml/`.

## Acompanhar inferências da aplicação

Para medidores cadastrados com intervalo esperado inferior a cinco minutos, o worker agrupa as leituras em janelas fixas de cinco minutos. Isso inclui o ESP32 cadastrado com cadência de 30 segundos. O worker calcula o consumo pela diferença do contador acumulado entre os pontos finais de janelas consecutivas e divide pelo tempo observado para obter a vazão média. A inferência fica associada à última leitura válida da janela e aguarda um intervalo esperado após o fechamento. Cobertura insuficiente, lacunas, volume ausente e queda no contador deixam a janela como não avaliada. Leituras atrasadas ficam no histórico. Uma janela já avaliada não é reprocessada pela mesma versão. Medidores com cadência de cinco minutos ou mais seguem com inferência por leitura.

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
