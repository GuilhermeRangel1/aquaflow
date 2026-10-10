# AquaFlow

O AquaFlow é uma aplicação para acompanhar o consumo de água de uma propriedade. Medidores conectados enviam leituras para a API; o sistema preserva os eventos recebidos, calcula o consumo entre leituras compatíveis e destaca comportamentos que merecem verificação.

Uma anomalia é um sinal para investigar. O AquaFlow não afirma localizar fisicamente um vazamento.

## O que o MVP já faz

- Cria conta e autentica usuários com senha protegida, access token e renovação de sessão.
- Organiza medidores e leituras por propriedade, com isolamento entre proprietários.
- Permite cadastrar, editar e retirar medidores sem apagar o histórico de telemetria.
- Recebe leituras individuais ou em lote. Reenvios com o mesmo identificador não duplicam consumo.
- Calcula séries de consumo a partir de vazão instantânea ou volume acumulado, considerando o fuso da propriedade e sem transformar lacunas em consumo zero.
- Apresenta resumo de consumo, histórico, saúde dos medidores e evidências das anomalias.
- Permite reconhecer, resolver ou marcar alertas como falso positivo; as transições ficam registradas.
- Oferece configurações de propriedade, incluindo endereço, fuso horário e parâmetros de monitoramento.
- Inclui dados sintéticos para explorar o dashboard sem hardware.

### Regras de monitoramento

- **Fluxo contínuo:** vazão acima do limite configurado — por padrão, `0,1 L/min` — por pelo menos 360 minutos. Leituras inválidas ou lacunas longas interrompem a janela.
- **Consumo noturno:** entre 22h e 6h no fuso da propriedade, fluxo pelo menos `0,1 L/min` acima da mediana diurna recente por 15 minutos consecutivos. Sem dados suficientes para a referência, não gera alerta.
- **Medidor offline:** ausência de leitura por mais de dois intervalos esperados. O alerta é encerrado quando o medidor volta a enviar dados.

Os alertas guardam a regra aplicada, a explicação e as evidências usadas. Recorrências podem gerar novos alertas depois que o anterior é encerrado.

## Executar com Docker Compose

Requisitos: Docker Desktop instalado e em execução. Reserve pelo menos 4 GB de memória para o Docker Desktop; o Airflow é mais pesado que os demais serviços.

Na raiz do projeto, execute:

```powershell
docker compose up --build
```

Quando os serviços estiverem prontos, acesse:

- Aplicação: [http://localhost:3000](http://localhost:3000)
- Documentação interativa da API: [http://localhost:8000/docs](http://localhost:8000/docs)
- Verificação de prontidão da API: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- Interface de experimentos MLflow: [http://localhost:5000](http://localhost:5000)

O Compose inicia PostgreSQL, API, frontend, broker MQTT, consumidor de mensagens, Airflow e MLflow, aplica as migrations e prepara os dados demonstrativos. Se ainda não houver um modelo treinado em `data/ml/training/`, também gera e prepara os dados mockados, treina os modelos e inicia o worker de inferência ao terminar. Se o artefato já existir, o treinamento é ignorado. O Airflow fica em [http://localhost:8080](http://localhost:8080), sem tela de login, e o MLflow registra os experimentos em [http://localhost:5000](http://localhost:5000). As duas interfaces ficam disponíveis apenas no computador local. Para executar em segundo plano, use `docker compose up --build -d`; para acompanhar a saída depois, use `docker compose logs -f`.

Para parar os serviços sem apagar o banco, pressione `Ctrl+C` no terminal ou execute `docker compose down`. O volume do PostgreSQL é preservado entre inicializações. Para apagar também o banco local e recriar a demonstração do zero, execute `docker compose down --volumes`.

### Acesso de demonstração

- **E-mail:** `demo@example.com`
- **Senha:** `AquaFlow-demo-123!`
- **Propriedade:** Casa da demonstração

Essas credenciais servem somente para desenvolvimento local. O seed sintético é habilitado por padrão no Compose e não pode ser usado em ambiente de produção. Para alterar o e-mail ou a senha da demonstração, defina `DEMO_USER_EMAIL` e `DEMO_USER_PASSWORD` no `.env` antes de iniciar os serviços. Consulte `.env.example`.

## Explorar os dados demonstrativos

A conta de demonstração é preparada automaticamente pelo serviço da API e contém:

- Três medidores ativos: consumo doméstico, irrigação e uma demonstração dedicada à inferência de ML.
- Histórico variável de aproximadamente 90 dias para consumo doméstico e sessões programadas de irrigação.
- Uma sequência curta de leituras normais e picos simulados no medidor de ML; com o worker experimental e um modelo treinado disponíveis, as previsões positivas são agrupadas em um alerta com evidências.
- Um alerta de fluxo contínuo produzido pelo detector por regras, além de poucos exemplos históricos para demonstrar os estados de tratamento.
- Leituras de bateria, sinal e versão de firmware nos dispositivos simulados.

O seed é aditivo e idempotente: ele acrescenta dados que ainda não existem e preserva a telemetria e o histórico. Os antigos medidores de reserva e lavanderia são desativados, sem apagar os registros. Para ver os alertas experimentais de ML, aguarde o treinamento automático terminar; o worker então avalia as leituras armazenadas e as novas leituras. Para experimentar ingestão de ponta a ponta, abra **Medidores**, cadastre um medidor com número de série exclusivo e use **Simular leituras**. O simulador envia eventos pela mesma API usada por um dispositivo.

## Integração com ESP32

A API já aceita telemetria autenticada por chave individual do dispositivo. O firmware e a calibração dependem da placa e do sensor escolhidos para o protótipo. O projeto não presume pinos, modelo de sensor ou fator de calibração.

O guia [Integração de um ESP32](firmware/docs/integracao-esp32.md) explica como provisionar um medidor, enviar uma leitura para a API local e testar o contrato sem firmware. A pasta [firmware](firmware/README.md) reúne o direcionamento para o futuro código FreeRTOS. No computador, a API fica em `http://localhost:8000`; um ESP32 precisa usar o endereço IP local da máquina que executa o Docker.

## Aquisição MQTT e dados para ML

O Compose também oferece um broker MQTT interno e um consumidor que encaminha as mensagens para a ingestão HTTP existente. Cadastre um medidor em **Medidores**, copie a chave mostrada e siga o [contrato MQTT](docs/contrato-mqtt.md) para publicar leituras de teste e consultá-las na aplicação. O broker não publica uma porta no host.

O [módulo de ML](ml/README.md) gera séries temporais reproduzíveis, prepara os dados e compara modelos offline. Na primeira inicialização sem artefato treinado, o Compose gera os dados, executa análise e preparação e treina os modelos; depois inicia o worker, que grava inferências experimentais para novas leituras. Para forçar outro treinamento, use `docker compose run --build --rm -e ML_RETRAIN_MODEL=true ml-trainer`. Uma previsão positiva cria um alerta experimental tratável, enquanto previsões normais permanecem registradas sem alerta. Os rótulos descrevem cenários simulados e não representam vazamentos confirmados. A interface local do Airflow é iniciada pelo comando padrão do Compose; habilite o DAG e execute-o manualmente para repetir o pipeline Airflow. O acesso sem login é apenas para desenvolvimento local e a porta fica vinculada ao próprio computador.

## Tecnologias e organização

- **Frontend:** Next.js, React, TypeScript e Recharts.
- **API:** Python 3.12+, FastAPI, Pydantic e SQLAlchemy assíncrono.
- **Banco:** PostgreSQL 16, com migrations Alembic.
- **Aquisição MQTT local:** Mosquitto e cliente Paho Python.
- **Execução local:** Docker Compose.

```text
backend/    API, domínio, persistência, migrations e testes
docs/       especificações, contrato MQTT e documentação transversal
firmware/   integração ESP32 e futuro código FreeRTOS
frontend/   aplicação web e dashboard
infrastructure/  configuração do broker MQTT
ml/         dados simulados, análise, preparação e comparação offline de modelos
```

O MVP é um monólito modular: a API reúne autenticação, propriedades, dispositivos, telemetria, consumo e alertas, mantendo os dados no PostgreSQL.

## Desenvolvimento local sem Compose

O fluxo recomendado para testar o produto é o Docker Compose. Para desenvolver os serviços separadamente, mantenha um PostgreSQL compatível com a configuração local disponível.

### API

No PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+asyncpg://aquaflow:aquaflow-local@localhost:5432/aquaflow"
$env:JWT_SECRET = "local-only-change-this-secret"
alembic upgrade head
python -m app.demo_seed
uvicorn app.main:app --reload
```

### Frontend

Em outro terminal:

```powershell
cd frontend
npm ci
$env:AQUAFLOW_API_URL = "http://localhost:8000"
npm run dev
```

## Verificações de desenvolvimento

Os comandos abaixo executam as verificações disponíveis no repositório:

```powershell
cd backend
python -m pytest -q
ruff check app tests migrations
mypy app
cd ..\frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Por padrão, os testes da API usam SQLite em memória. Para executá-los contra o PostgreSQL do Compose, use na raiz do projeto:

```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test run --build --rm tests
```

O serviço de testes usa dependências de desenvolvimento e a mesma suíte HTTP, criando um schema temporário isolado por fixture e removendo-o ao terminar. O usuário PostgreSQL configurado precisa poder criar e remover schemas.

## Estado e próximos passos

O MVP cobre a jornada principal com API e dados sintéticos: autenticação, gestão de propriedade e medidores, ingestão, consumo, detecção baseada em regras e tratamento de alertas. O dashboard e o Compose permitem explorar essa jornada sem hardware.

Ainda dependem de evolução do projeto:

- Firmware do ESP32 e calibração com o sensor físico escolhido.
- Validação de ponta a ponta com hardware e rede reais.
- Ampliação da cobertura de integração com PostgreSQL.
- Análise exploratória, preparação, comparação de modelos com registro no MLflow e inferência experimental integrada estão disponíveis para dados simulados. Previsões positivas geram alertas experimentais separados dos detectores por regras. O worker é opcional e ainda falta validação com telemetria real; as métricas atuais não representam desempenho em vazamentos reais.
- Notificações externas e compartilhamento de propriedade, que estão fora do escopo atual.
