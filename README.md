# AquaFlow

O AquaFlow é um **protótipo acadêmico** para acompanhar consumo de água. Ele integra uma interface web, uma API, PostgreSQL, ingestão de telemetria por HTTP ou MQTT, monitoramento por regras e um experimento de machine learning.

A aplicação pode ser explorada sem hardware: a conta demo e os experimentos de ML usam dados mockados. Os rótulos do modelo indicam cenários artificiais definidos pelo gerador; não representam vazamentos confirmados. O projeto ainda não tem firmware ESP32 implementado nem foi validado com medidores físicos. Consulte [estado atual e limitações](docs/estado-do-projeto.md).

## Navegação

| Guia | Conteúdo |
| --- | --- |
| [Como executar e demonstrar](docs/demonstracao.md) | Compose, conta demo, primeiro início, publicação MQTT e comandos de operação. |
| [Arquitetura](docs/arquitetura.md) | Serviços, fluxos HTTP/MQTT, regras, treinamento e inferência. |
| [Estado do projeto](docs/estado-do-projeto.md) | O que funciona no protótipo e o que ainda não foi validado ou implementado. |
| [Dados e modelos](ml/README.md) | Dados simulados, Airflow, MLflow, notebook, treinamento e inferência. |
| [Contrato MQTT](docs/contrato-mqtt.md) | Tópicos, autenticação e payload publicado no broker local. |
| [Integração ESP32](firmware/README.md) | Limites atuais e direcionamento do futuro firmware. |
| [Especificação](especificacao-monitoramento-consumo-agua.md) | Requisitos e contratos de referência do produto. |
| [Glossário](docs/glossary.md) | Termos do domínio usados no repositório. |

## O que o protótipo demonstra

- Cadastro e autenticação de uma conta, propriedade e medidores.
- Ingestão de leituras, armazenamento das amostras brutas e cálculo de consumo sem transformar lacunas em consumo zero.
- Monitoramento por regras explicáveis e tratamento de alertas: reconhecer, resolver ou marcar falso positivo.
- Entrada MQTT encaminhada para a mesma API HTTP usada pela ingestão direta.
- Dashboard com consumo, histórico, dispositivos, alertas, inferências experimentais e saúde dos serviços.
- Pipeline reproduzível de análise e preparação de dados mockados, comparação de modelos, registro no MLflow e inferência.

Esses fluxos mostram a integração do protótipo. Não atestam medição física, desempenho de ML em residências ou prontidão para uso em produção. O modelo não substitui os detectores por regras; previsões positivas podem aparecer como alertas experimentais separados.

## Executar com Docker Compose

Requisitos: Docker Desktop com suporte a Docker Compose v2 e memória suficiente para os serviços da aplicação, do Airflow e do treinamento.

Na raiz do repositório:

```powershell
docker compose up --build
```

Na primeira inicialização, o Compose inicia PostgreSQL, API, interface, broker MQTT, consumidor MQTT, Airflow e MLflow. A API aplica migrations e prepara os dados sintéticos da demo. Se ainda não houver um modelo treinado em `data/ml/training/`, o serviço de treinamento gera outra série mockada, analisa e prepara os registros, compara os modelos e registra os resultados no MLflow. Depois, o worker de inferência processa leituras compatíveis. O treinamento pode levar alguns minutos; o serviço `ml-trainer` termina normalmente depois de concluir. Se os artefatos já existirem, ele os reutiliza.

Acesse:

- **AquaFlow:** [http://localhost:3000](http://localhost:3000)
- **API e OpenAPI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prontidão da API:** [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- **Experimentos MLflow:** [http://localhost:5000](http://localhost:5000)
- **Airflow:** [http://localhost:8080](http://localhost:8080)

Airflow e MLflow ficam vinculados ao computador local; o broker MQTT não publica uma porta no host. Ainda assim, esta configuração inteira é para desenvolvimento local, com credenciais demonstrativas. Não a exponha à internet.

### Conta demonstrativa

```text
E-mail: demo@example.com
Senha: AquaFlow-demo-123!
Propriedade: Casa da demonstração
```

Para trocar e-mail e senha, configure `DEMO_USER_EMAIL` e `DEMO_USER_PASSWORD` no arquivo `.env`; para alterar as demais credenciais locais, use também os valores de `.env.example`. Os padrões servem somente para desenvolvimento.

### Encerrar e reiniciar

- `Ctrl+C` ou `docker compose down`: encerra os serviços e preserva volumes e arquivos locais.
- `docker compose logs -f ml-trainer ml-inference api mqtt-ingestor`: acompanha o treinamento e os processos centrais.
- `docker compose down --volumes`: também apaga os volumes nomeados, inclusive o banco e o estado local do broker/Airflow. Use apenas para recriar esses dados locais; os arquivos em `data/` podem permanecer.

O passo a passo e a demonstração MQTT estão em [docs/demonstracao.md](docs/demonstracao.md).

## Como interpretar os dados e resultados

Existem dados sintéticos para a demonstração visual da aplicação e uma série separada para treinamento de ML. O gerador de ML cria rótulos para cenários conhecidos, separa treino/validação/teste em ordem temporal e produz perfis artificiais para examinar mudanças de rotina. O notebook de exploração e avaliação visualiza a preparação, comparação, matriz de confusão e curvas precisão-recall/ROC.

As métricas medem apenas o reconhecimento dos cenários que o próprio simulador criou. Elas não informam a taxa real de vazamentos detectados, não comprovam generalização e não demonstram ausência de overfitting. Para mudar esse estado será necessário coletar telemetria física, definir rótulos ou uma avaliação sem rótulos apropriada e refazer a avaliação em dados independentes. Mais detalhes em [ml/README.md](ml/README.md) e [docs/estado-do-projeto.md](docs/estado-do-projeto.md).

## Regras de monitoramento

- **Fluxo contínuo:** vazão acima do limite configurado durante a janela sustentada.
- **Consumo noturno:** elevação persistente em relação à referência diurna, no horário local da propriedade.
- **Medidor offline:** ausência de leituras por mais de dois intervalos esperados.

As regras guardam explicações e evidências. Os limites padrão, as condições de dados insuficientes e os contratos estão descritos na [especificação](especificacao-monitoramento-consumo-agua.md) e no [guia de demonstração](docs/demonstracao.md). Um alerta sinaliza algo a verificar; não localiza fisicamente um vazamento.

## Organização do repositório

```text
backend/          API, domínio, persistência, migrations e testes
frontend/         Interface web Next.js, React, TypeScript e Recharts
ml/               Geração sintética, preparação, modelos e inferência
firmware/         Contratos e guia para o futuro firmware ESP32/FreeRTOS
docs/             Arquitetura, estado, demonstração e contratos
infrastructure/   Configuração local do broker MQTT
docker-compose.yml
```

A arquitetura detalhada e os limites entre componentes estão em [docs/arquitetura.md](docs/arquitetura.md).

## Desenvolvimento e verificações

O caminho mais simples para explorar o produto é Docker Compose. Para desenvolvimento local dos serviços, consulte as dependências em `backend/pyproject.toml` e `frontend/package.json` e mantenha PostgreSQL compatível disponível.

Verificações da API e do frontend:

```powershell
cd backend
python -m pytest -q
ruff check app tests migrations
mypy app
cd ..\frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Para executar a suíte HTTP contra um PostgreSQL isolado pelo Compose:

```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test run --build --rm tests
```

O notebook tem dependências locais próprias. Veja [instruções de ML](ml/README.md#notebook-de-exploração-e-avaliação-visual); elas não são incluídas na imagem usada pela aplicação.
