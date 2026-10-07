# AquaFlow

Plataforma de monitoramento de consumo de água. A API recebe telemetria autenticada por dispositivo, preserva as leituras brutas e calcula consumo entre amostras compatíveis. O dashboard mostra o total e o histórico diário, sem tratar intervalos sem dados como consumo zero.

## MVP implementado

- Cadastro e login com senha Argon2id, access token JWT e refresh token rotativo.
- Cadastro de propriedade com fuso IANA e unidade em litros.
- Provisionamento de medidor com chave individual; a chave é mostrada uma vez e apenas o hash fica no banco.
- Ingestão individual e em lote, com idempotência por dispositivo e `event_id`.
- Leituras acumuladas e vazão instantânea, com agregação por hora, dia ou mês.
- Dashboard responsivo e simulador de leituras para demonstração.
- Migração inicial Alembic e ambiente de desenvolvimento via Docker Compose.

## Executar com Docker

1. Execute `.\run-aquaflow.ps1` no PowerShell ou dê duplo clique em `run-aquaflow.bat`. Na primeira execução, o script cria `.env` com segredos locais aleatórios e tenta abrir o Docker Desktop se o daemon não estiver ativo.
2. Aguarde o build e a inicialização dos serviços.
3. Acesse o dashboard em `http://localhost:3000` e a documentação OpenAPI em `http://localhost:8000/docs`.

Para parar a aplicação, pressione `Ctrl+C` no terminal do script ou execute `.\stop-aquaflow.ps1`. O volume do PostgreSQL é preservado; para remover também o banco local, use `docker compose down --volumes`.

O serviço da API aplica `alembic upgrade head` antes de iniciar. O PostgreSQL usa volume nomeado para preservar os dados entre reinícios.

## Executar localmente

### API

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+asyncpg://aquaflow:aquaflow-local@localhost:5432/aquaflow"
$env:JWT_SECRET = "local-only-change-this-secret-before-deploy"
alembic upgrade head
uvicorn app.main:app --reload
```

### Dashboard

```powershell
cd frontend
npm ci
$env:AQUAFLOW_API_URL = "http://localhost:8000"
npm run dev
```

## Fluxo de demonstração

1. Crie uma conta e cadastre uma propriedade.
2. Provisione um medidor com número de série único.
3. Copie a chave exibida. O AquaFlow não a armazena em texto aberto e não poderá exibi-la de novo.
4. Use “Simular leituras de demonstração” para enviar três amostras pela mesma rota autenticada que um dispositivo usaria.
5. O resumo do imóvel e o gráfico diário são atualizados pela API.

Leituras atrasadas dentro da janela configurada são aceitas; relógios mais de cinco minutos no futuro são rejeitados. Fluxo instantâneo só gera volume quando há amostras consecutivas dentro de duas vezes o intervalo esperado.

## Verificações

```powershell
cd backend
python -m pytest -q
ruff check app tests migrations
mypy app
cd ..\frontend
npm run lint
npm run build
```

Os testes de API usam SQLite assíncrono para não depender de serviço externo. A migração foi validada em modo SQL offline; a execução contra PostgreSQL depende do Docker/servidor estar disponível.

## Próximas fatias

O núcleo de ingestão e consumo é o primeiro fluxo ponta a ponta. As próximas entregas são regras explicáveis e ciclo de vida de alertas, controles de configuração, observabilidade operacional e validação de integração em PostgreSQL. Firmware ESP32, alertas externos e compartilhamento entre usuários permanecem fora do MVP atual.
