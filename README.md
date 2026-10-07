# AquaFlow

Plataforma de monitoramento de consumo de água. A API recebe telemetria autenticada por dispositivo, preserva as leituras brutas e calcula consumo entre amostras compatíveis. O dashboard mostra o total e o histórico diário, sem tratar intervalos sem dados como consumo zero.

## MVP implementado

- Cadastro e login com senha Argon2id, access token JWT e refresh token rotativo.
- Cadastro de propriedade com fuso IANA e unidade em litros.
- Provisionamento de medidor com chave individual; a chave é mostrada uma vez e apenas o hash fica no banco.
- Ingestão individual e em lote, com idempotência por dispositivo e `event_id`.
- Leituras acumuladas e vazão instantânea, com agregação por hora, dia ou mês.
- Detecção explicável de fluxo contínuo e alertas agrupados, com reconhecimento, resolução e marcação como falso positivo.
- Dashboard responsivo e simulador de leituras para demonstração.
- Migrations Alembic e ambiente de desenvolvimento via Docker Compose.

## Executar com Docker

Com o Docker Desktop aberto, execute na raiz do projeto:

```powershell
docker compose up --build
```

Quando os serviços ficarem prontos, abra `http://localhost:3000`. A API e sua documentação OpenAPI ficam em `http://localhost:8000/docs`.

Para parar, pressione `Ctrl+C` ou execute `docker compose down`. O volume do PostgreSQL é preservado; para reiniciar a demonstração do zero e apagar os dados locais, use `docker compose down --volumes`.

O serviço da API aplica `alembic upgrade head` e prepara os dados sintéticos antes de iniciar. O PostgreSQL usa volume nomeado para preservar os dados entre reinícios. A demonstração local pode ser desativada com `DEMO_MODE=false` no `.env`.

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

No Compose local, entre com a conta sintética `demo@example.com` e a senha `AquaFlow-demo-123!`. A conta traz uma propriedade, leituras diárias de três medidores ativos, um medidor sem comunicação e exemplos de alertas abertos, reconhecidos, resolvidos e marcados como falso positivo. Os alertas de amostra são identificados como dados demonstrativos; o alerta de fluxo contínuo é gerado pela regra real. O seed é aditivo e idempotente: ao iniciar uma base que já contém a conta demo, acrescenta apenas os exemplos ausentes e preserva os dados existentes. Uma base criada por versão anterior migra o e-mail local da conta demo automaticamente para o endereço de exemplo aceito pelo validador.

Para testar também o cadastro e a ingestão, adicione outro medidor com número de série ainda não usado. A chave é exibida uma única vez; use “Simular leituras” para enviar eventos pela mesma rota de telemetria do dispositivo. A lista, os indicadores e o gráfico atualizam pela API.

Essas credenciais são apenas para desenvolvimento local. O seed não roda em `ENVIRONMENT=production` e a API rejeita `DEMO_MODE=true` nesse ambiente.

### Regra inicial de fluxo contínuo

O primeiro detector considera uma anomalia quando a vazão média entre amostras válidas fica acima de `0,1 L/min` por pelo menos `360 minutos`. O limite e a duração podem ser informados ao criar a propriedade pelos campos `continuous_flow_threshold_liters_minute` e `continuous_flow_duration_minutes`; esses valores também ficam registrados como evidência. Lacunas acima de duas vezes o intervalo esperado ou leituras inválidas interrompem a janela. Leituras com vazão instantânea e volume acumulado são aceitas.

Quando a janela é atingida, a ingestão persiste uma anomalia e abre um alerta de severidade alta. Novas detecções da mesma regra e dispositivo são agrupadas enquanto o alerta estiver aberto ou reconhecido. Os endpoints de consulta são `GET /api/v1/properties/{property_id}/anomalies`, `GET /api/v1/anomalies/{anomaly_id}` e `GET /api/v1/properties/{property_id}/alerts`. O proprietário pode usar `POST /api/v1/alerts/{alert_id}/acknowledge`, `/resolve` ou `/false-positive`; uma recorrência após o encerramento cria outro alerta.

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

Os testes de API usam SQLite assíncrono para não depender de serviço externo. A migração adicionada para anomalias e alertas deve ser aplicada pelo serviço da API na inicialização do Compose.

## Próximas fatias

O fluxo de ingestão, consumo, primeira regra/alerta, gestão de estado da fila e dados de demonstração estão implementados. As próximas entregas são regras noturnas e de dispositivo offline, configurações editáveis, comparativos, observabilidade operacional e validação de integração em PostgreSQL. Firmware ESP32, alertas externos e compartilhamento entre usuários permanecem fora do MVP atual.
