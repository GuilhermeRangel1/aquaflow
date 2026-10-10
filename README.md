# AquaFlow

**AquaFlow é um protótipo acadêmico de monitoramento do consumo de água.** Ele integra uma aplicação web, uma API, PostgreSQL, ingestão de telemetria por HTTP e MQTT, monitoramento por regras e um experimento de machine learning.

O protótipo pode ser demonstrado sem medidores físicos. A conta de demonstração e o treinamento usam dados mockados gerados separadamente pelo projeto. Os rótulos do modelo representam cenários artificiais — não vazamentos observados. Ainda não há firmware ESP32/FreeRTOS implementado nem validação em uma instalação real.

## Navegação rápida

| Guia | O que você encontra |
| --- | --- |
| [Como executar](docs/demonstracao.md) | Inicialização com Docker Compose, conta de demonstração e comandos do fluxo principal. |
| [Arquitetura](docs/arquitetura.md) | Serviços, caminhos de dados e decisões da integração. |
| [Estado atual](docs/estado-do-projeto.md) | O que está implementado, o que é experimental e o que falta validar. |
| [Métricas e parâmetros](docs/metricas-e-parametros.md) | Limites, valores padrão e métricas usados no projeto. |
| [Resultado do experimento ML](ml/docs/resultado-experimento.md) | Execução de referência, comparação de modelos e limitações. |
| [Dados e modelos](ml/README.md) | Geração mockada, pipeline, notebook, treinamento e inferência. |
| [Contrato MQTT](docs/contrato-mqtt.md) | Tópicos, autenticação e payload aceito pelo broker local. |
| [Especificação](especificacao-monitoramento-consumo-agua.md) | Requisitos e contratos de referência do produto e da API. |


### Resumo do consumo

![Resumo do consumo na visão geral do AquaFlow](docs/images/resumo-do-consumo.png)

### Acompanhamento e análises

![Acompanhamento e análises na visão geral do AquaFlow](docs/images/acompanhamento-e-analises.png)

## Visão geral

O AquaFlow recebe leituras de medidores, preserva os eventos recebidos, calcula consumo entre amostras compatíveis e mostra a evolução no dashboard. Regras determinísticas identificam comportamentos que merecem verificação. O classificador experimental de ML é avaliado em paralelo e não substitui essas regras.

```mermaid
flowchart LR
    Medidor[Cliente HTTP ou simulador] --> API[API AquaFlow]
    Simulador[Publicador MQTT de teste] --> Broker[Broker MQTT local]
    Broker --> Ingestor[Consumidor MQTT]
    Ingestor --> API
    API --> DB[(PostgreSQL)]
    DB --> Worker[Worker experimental de ML]
    Worker --> DB
    DB --> API
    API --> Frontend[Dashboard web]
```

Esse desenho representa a integração de desenvolvimento local. O detalhe dos serviços, contratos e limites atuais está em [Arquitetura](docs/arquitetura.md).

## O que o protótipo demonstra

- Conta demonstrativa com propriedade, medidores, histórico sintético e exemplos de alertas.
- Cadastro e acompanhamento de medidores, ingestão HTTP e consulta de leituras.
- Ingestão MQTT encaminhada para a mesma API HTTP de validação e persistência.
- Cálculo de consumo entre leituras compatíveis, mantendo lacunas sem tratá-las como consumo zero.
- Alertas por regras explicáveis, com evidências e ações de reconhecimento, resolução e falso positivo.
- Experimento de classificação binária, execução de inferência integrada e alertas experimentais separados dos alertas por regras.
- Pipeline reprodutível com geração, análise e preparação dos dados, comparação de modelos, registro no MLflow e dashboard.

Essas funções mostram o funcionamento integrado do protótipo. Elas não comprovam medição física, desempenho de ML em residências nem prontidão para produção.

## Início rápido

### Requisitos

- Docker Desktop com Docker Compose v2.
- Portas locais `3000`, `5000`, `5432`, `8000` e `8080` disponíveis.
- Memória suficiente para a aplicação, o Airflow e o treinamento inicial. A geração do modelo pode levar alguns minutos.

Na raiz do repositório, inicie a solução completa:

```powershell
docker compose up --build
```

Na primeira execução, o Compose constrói e inicia PostgreSQL, API, dashboard, broker MQTT, consumidor MQTT, Airflow e MLflow. A API aplica as migrations e popula a conta demonstrativa. Se o modelo ainda não existir, o serviço `ml-trainer` gera uma série sintética, executa análise e preparação, compara modelos e registra o experimento. O treinamento termina normalmente; depois dele, `ml-inference` inicia e processa leituras compatíveis. Nas próximas execuções, os artefatos locais existentes são reutilizados.

| Serviço | Endereço local |
| --- | --- |
| Dashboard AquaFlow | [http://localhost:3000](http://localhost:3000) |
| API e documentação OpenAPI | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Prontidão da API | [http://localhost:8000/health/ready](http://localhost:8000/health/ready) |
| Experimentos MLflow | [http://localhost:5000](http://localhost:5000) |
| Interface Airflow | [http://localhost:8080](http://localhost:8080) |

O acesso ao Airflow e ao MLflow é local. O broker MQTT não publica sua porta no computador. Esta configuração usa credenciais de desenvolvimento e não deve ser exposta à internet.

### Conta de demonstração

```text
E-mail: demo@example.com
Senha: AquaFlow-demo-123!
Propriedade: Casa da demonstração
```

Para mudar o e-mail ou a senha, copie `.env.example` para `.env` e altere `DEMO_USER_EMAIL` e `DEMO_USER_PASSWORD` antes de iniciar. Os valores padrão são destinados apenas à máquina local.

### O que você verá

A conta demo contém três medidores ativos, leituras sintéticas, alertas de exemplo em estados diferentes e uma pequena sequência de leituras para mostrar a inferência. O seed é aditivo e preserva o histórico do banco ao reiniciar o serviço. Esses dados não vieram de sensores físicos.

Na aba de acompanhamento, alertas de regras e análises experimentais de ML aparecem separados. Uma previsão positiva pode abrir um alerta experimental tratável; isso não muda os detectores por regras. Resultados insuficientes indicam que faltam dados válidos para calcular as features necessárias, e não que o modelo previu comportamento normal. Veja [como executar e demonstrar](docs/demonstracao.md) para os passos de MQTT, Airflow, logs e reinicialização.

## Como entram e são tratados os dados

### HTTP

Um dispositivo provisionado envia a leitura à API com seu número de série, um `event_id` estável, timestamp com fuso e volume acumulado, vazão instantânea ou ambos. A API valida a chave individual, verifica limites e timestamps, evita duplicar eventos reenviados e preserva a telemetria bruta. O consumo é calculado a partir de leituras válidas compatíveis.

### MQTT

O broker local recebe uma publicação no tópico do medidor. O consumidor valida a mensagem e encaminha a leitura para a API HTTP, que continua responsável por autenticação, validação, idempotência e armazenamento. Isso permite exercitar o fluxo sem hardware com o serviço `mqtt-publisher`.

Para os tópicos, o corpo JSON e uma publicação de exemplo, consulte o [contrato MQTT](docs/contrato-mqtt.md). Ele não valida conexão física nem substitui o futuro firmware.

### Regras de monitoramento

Os principais detectores atuais são fluxo contínuo acima do limite configurado, aumento persistente do consumo durante a janela noturna local e ausência de leituras por mais de dois intervalos esperados. As regras produzem explicações e evidências; seus padrões e condições estão em [Métricas e parâmetros](docs/metricas-e-parametros.md).

O AquaFlow sinaliza comportamentos que merecem verificação. Não confirma nem localiza fisicamente um vazamento.

## Experimento de machine learning

O primeiro modelo é um classificador binário por leitura válida. O gerador cria períodos normais, fluxo contínuo, consumo noturno e lacunas; `anomaly_label` marca os cenários artificiais. As features representam vazão, delta do volume acumulado, duração do intervalo e horário cíclico local. Identificadores, dados de bateria/sinal e rótulos não são entradas do modelo.

O treinamento usa 16 dias mockados, partição cronológica de 8/4/4 dias, validação cruzada temporal e comparação entre regressão logística, Random Forest, HistGradientBoosting e um baseline de prevalência. A seleção considera average precision na validação temporal e num perfil simulado com rotina alterada. Um perfil de estresse fica separado para avaliação posterior.

### Resultado de referência

Na execução reproduzida para este projeto, o Random Forest foi selecionado. No teste temporal do mesmo perfil sintético, teve AP `1,000`, precisão `0,994`, recall `1,000` e F1 `0,997`. Esse resultado alto não se manteve nos perfis de distribuição alterada: AP `0,438` em `shifted` e `0,569` em `stress`.

Essa diferença é central para interpretar o experimento: o modelo reconhece muito bem o gerador padrão, mas sua resposta piora com outras rotinas simuladas. As métricas não estimam detecção real e não permitem afirmar ausência de overfitting. O relatório registra as matrizes de confusão, parâmetros, hashes, versões do ambiente e comandos de reprodução em [Resultado do experimento](ml/docs/resultado-experimento.md).

### Airflow, treinamento e notebook

- **Airflow:** iniciado pelo Compose; o DAG deve ser habilitado e acionado manualmente. Ele gera, analisa e prepara uma série mockada, mas não inicia o treinamento.
- **Treinamento do Compose:** executa automaticamente quando o artefato não existe ou pode ser forçado com o comando descrito em [Dados e modelos](ml/README.md).
- **Notebook:** documenta a exploração e o preparo e gera gráficos de avaliação a partir do modelo treinado. Não substitui o pipeline nem envia seus gráficos ao dashboard.
- **Inferência na aplicação:** o worker avalia leituras persistidas com dados suficientes e registra a versão do modelo. As regras permanecem ativas se o worker falhar.

Para os valores de configuração, métricas, unidades e limitações do experimento, consulte [Métricas e parâmetros](docs/metricas-e-parametros.md). O [estado atual do projeto](docs/estado-do-projeto.md) explica o que será necessário para migrar de dados simulados para telemetria real.

## Configurações locais

As configurações opcionais ficam em `.env`. Use `.env.example` como modelo; mantenha o arquivo `.env` local e não compartilhe credenciais.

| Variável | Uso |
| --- | --- |
| `POSTGRES_PASSWORD` | Senha do banco local. |
| `JWT_SECRET` | Segredo usado para tokens de acesso; gere um valor próprio fora da demonstração local. |
| `DEMO_MODE` | Habilita a preparação da conta demonstrativa no ambiente local. |
| `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD` | Credenciais da conta demo. |
| `MQTT_PUBLISH_PASSWORD`, `MQTT_INGEST_PASSWORD` | Credenciais locais do publicador e do consumidor MQTT. |
| `ML_POLL_SECONDS` | Intervalo de consulta do worker de inferência, em segundos. |

Os padrões e os limites configuráveis são para desenvolvimento. Para não expor a instância, mantenha-a no computador local; os serviços não foram preparados como configuração de produção.

## Organização do repositório

```text
backend/          API FastAPI, domínio, persistência, migrations e testes
frontend/         Interface Next.js, React, TypeScript e Recharts
ml/               Dados sintéticos, preparação, modelos, inferência e notebook
firmware/         Contratos e guia para o futuro ESP32/FreeRTOS
docs/             Arquitetura, parâmetros, estado, demonstração e contratos
infrastructure/   Configuração local do broker MQTT
docker-compose.yml
```

## Desenvolvimento e verificações

O modo recomendado para executar a solução integrada é Docker Compose. Para desenvolvimento local, veja as dependências em `backend/pyproject.toml` e `frontend/package.json` e disponibilize um PostgreSQL compatível.

Para verificar a API:

```powershell
cd backend
python -m pytest -q
ruff check app tests migrations
mypy app
```

Para verificar o frontend:

```powershell
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Para executar a suíte HTTP com PostgreSQL isolado pelo Compose:

```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test run --build --rm tests
```

Para o ambiente do notebook e os comandos completos do pipeline, consulte [Dados e modelos](ml/README.md). As verificações e as métricas de referência devem sempre ser interpretadas conforme seus dados e limitações.

## Limites e próximos passos

- Não há firmware ESP32/FreeRTOS, placa, sensor ou calibração definidos.
- A ingestão MQTT foi exercitada com um publicador de teste na rede local do Compose; não há conexão física validada nem TLS para um dispositivo externo.
- A conta de demonstração e as séries de ML são sintéticas e independentes entre si.
- O classificador foi avaliado somente com cenários artificiais. Dados reais precisarão de coleta, verificação de qualidade, decisão de rotulagem e teste temporal independente.
- Airflow, MLflow, credenciais e serviços do Compose são configurados para apresentação local, não para produção.

Veja [Estado atual do projeto](docs/estado-do-projeto.md) para os detalhes das limitações e [Integração ESP32](firmware/README.md) para o que precisa ser definido antes de implementar o firmware.
