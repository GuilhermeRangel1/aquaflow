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

Requisitos: Docker Desktop instalado e em execução.

Na raiz do projeto, execute:

```powershell
docker compose up --build
```

Quando os serviços estiverem prontos, acesse:

- Aplicação: [http://localhost:3000](http://localhost:3000)
- Documentação interativa da API: [http://localhost:8000/docs](http://localhost:8000/docs)
- Verificação de prontidão da API: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

O Compose inicia PostgreSQL, API e frontend, aplica as migrations e prepara os dados demonstrativos. Para executar em segundo plano, use `docker compose up --build -d`; para acompanhar a saída depois, use `docker compose logs -f`.

Para parar os serviços sem apagar o banco, pressione `Ctrl+C` no terminal ou execute `docker compose down`. O volume do PostgreSQL é preservado entre inicializações. Para apagar também o banco local e recriar a demonstração do zero, execute `docker compose down --volumes`.

### Acesso de demonstração

- **E-mail:** `demo@example.com`
- **Senha:** `AquaFlow-demo-123!`
- **Propriedade:** Casa da demonstração

Essas credenciais servem somente para desenvolvimento local. O seed sintético é habilitado por padrão no Compose e não pode ser usado em ambiente de produção. Para alterar o e-mail ou a senha da demonstração, defina `DEMO_USER_EMAIL` e `DEMO_USER_PASSWORD` no `.env` antes de iniciar os serviços. Consulte `.env.example`.

## Explorar os dados demonstrativos

A conta de demonstração é preparada automaticamente pelo serviço da API e contém:

- Histórico variável de aproximadamente 90 dias para consumo doméstico.
- Um medidor principal, um medidor de irrigação com sessões programadas, um medidor de lavanderia e um medidor de reserva offline.
- Leituras de bateria, sinal e versão de firmware para os medidores simulados.
- Alertas de exemplo em diferentes estados, identificados como simulados, além de um alerta de fluxo contínuo gerado pelo detector.

O seed é aditivo e idempotente: ele acrescenta dados que ainda não existem e preserva os registros existentes. Para experimentar ingestão de ponta a ponta, abra **Medidores**, cadastre um medidor com número de série exclusivo e use **Simular leituras**. O simulador envia eventos pela mesma API usada por um dispositivo.

## Integração com ESP32

A API já aceita telemetria autenticada por chave individual do dispositivo. O firmware e a calibração dependem da placa e do sensor escolhidos para o protótipo. O projeto não presume pinos, modelo de sensor ou fator de calibração.

O guia [Integração de um ESP32](docs/integracao-esp32.md) explica como provisionar um medidor, enviar uma leitura para a API local e testar o contrato sem firmware. No computador, a API fica em `http://localhost:8000`; um ESP32 precisa usar o endereço IP local da máquina que executa o Docker.

## Tecnologias e organização

- **Frontend:** Next.js, React, TypeScript e Recharts.
- **API:** Python 3.12+, FastAPI, Pydantic e SQLAlchemy assíncrono.
- **Banco:** PostgreSQL 16, com migrations Alembic.
- **Execução local:** Docker Compose.

```text
backend/    API, domínio, persistência, migrations e testes
docs/       integração ESP32 e orientações específicas da API
frontend/   aplicação web e dashboard
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
- Histórico real com qualidade suficiente para avaliar métodos estatísticos ou machine learning. O MVP atual usa regras explicáveis; ML não decide alertas.
- Notificações externas e compartilhamento de propriedade, que estão fora do escopo atual.
