# Especificacao do Projeto de Monitoramento de Consumo de Agua

**Versao:** 1.0  
**Data:** 22 de setembro de 2026  
**Status:** base tecnica para MVP e evolucao do produto

## 1. Visao geral

Este projeto transforma dados de consumo de agua em informacoes claras e uteis, permitindo que o usuario acompanhe melhor seu consumo, compreenda alteracoes no comportamento habitual e perceba possiveis anomalias com maior antecedencia. A solucao apoia decisoes mais rapidas, reduz desperdicios e contribui para um uso mais consciente da agua.

O produto recebe telemetria de medidores conectados, armazena leituras com rastreabilidade, calcula agregacoes de consumo, identifica comportamentos fora do padrao e apresenta um painel web para acompanhamento. O sistema nao afirma, sozinho, onde esta um vazamento: ele sinaliza que o comportamento observado merece verificacao.

### 1.1 Objetivos

- Receber leituras do ESP32 de forma segura, idempotente e resiliente a falhas de rede.
- Exibir consumo atual, historico, comparativos e tendencia.
- Detectar anomalias em camadas, comecando por regras explicaveis.
- Gerar alertas acionaveis, com severidade, evidencias e estado de tratamento.
- Permitir evolucao para estatistica avancada e modelos de machine learning sem reescrever o nucleo.
- Entregar uma base de codigo testavel, observavel e facil de evoluir por uma equipe humana ou por agentes de IA.

### 1.2 Escopo do MVP

O MVP deve contemplar autenticacao, cadastro de propriedades e dispositivos, ingestao de telemetria, consulta de consumo horario e diario, regras de deteccao de anomalias, alertas no painel, dashboard web responsivo, Docker Compose, migrations e testes automatizados.

Ficam fora do MVP: comando remoto para fechar valvula, faturamento, integracao com concessionarias, previsao de tarifa, classificacao de vazamento por local fisico e modelos de IA generativa que tomem decisoes sem explicacao.

## 2. Arquitetura da solucao

```text
ESP32 / medidor de vazao
          |
          | HTTPS + JSON
          v
    API FastAPI
  auth | devices | telemetry
  consumption | anomalies | alerts
          |
          +---------------------> PostgreSQL
          |                         |
          |                         +--> leituras brutas
          |                         +--> agregacoes
          |                         +--> anomalias e alertas
          |
          +---------------------> Worker de analise (fase 2)
          |
          v
 Next.js + TypeScript + Tailwind + shadcn/ui
          |
          v
 Dashboard para acompanhamento e resposta
```

### 2.1 Decisoes de arquitetura

1. **Monolito modular no MVP:** API, dominio e persistencia ficam em um unico servico, com limites internos claros. Isso reduz complexidade operacional sem impedir uma separacao futura.
2. **PostgreSQL como fonte de verdade:** leituras brutas nao sao sobrescritas por agregacoes ou deteccoes.
3. **Processamento incremental:** a API registra a leitura rapidamente; agregacoes e analises podem ser executadas em segundo plano quando o volume exigir.
4. **Camadas de deteccao desacopladas:** regras, estatistica e ML implementam a mesma interface de detector e produzem evidencias comparaveis.
5. **Frontend orientado a decisao:** o painel prioriza o que mudou, o que merece atencao e qual acao o usuario pode tomar.

## 3. Stack tecnologica

### Backend

| Area | Tecnologia | Uso |
|---|---|---|
| Runtime | Python 3.12+ | linguagem principal |
| API | FastAPI | endpoints REST, OpenAPI e validacao |
| Modelos | Pydantic v2 | contratos de entrada e saida |
| ORM | SQLAlchemy 2.x | mapeamento e consultas |
| Migrations | Alembic | versionamento do schema |
| Banco | PostgreSQL 16+ | persistencia transacional |
| Driver | asyncpg | conexao assincrona |
| Autenticacao | JWT + Argon2id | sessoes e senhas |
| Testes | pytest, pytest-asyncio, httpx | unidade, integracao e API |
| Qualidade | Ruff, mypy | lint, formatacao e tipos |

### Frontend

| Area | Tecnologia | Uso |
|---|---|---|
| Framework | Next.js com App Router | aplicacao web |
| Linguagem | TypeScript | tipagem e manutencao |
| Estilo | Tailwind CSS | tokens e composicao visual |
| Componentes | shadcn/ui | componentes acessiveis e consistentes |
| Dados | TanStack Query | cache, loading, retry e invalidacao |
| Formularios | React Hook Form + Zod | formularios e validacao |
| Graficos | Recharts | series de consumo e comparativos |
| Icones | Lucide | linguagem visual consistente |

### Infraestrutura

Docker Compose no desenvolvimento, PostgreSQL gerenciado ou containerizado, proxy TLS em producao, armazenamento de logs centralizado e job scheduler. Redis e um worker dedicado entram na fase em que a ingestao ou a analise deixarem de ser confortaveis no ciclo da requisicao.

## 4. Requisitos funcionais

### RF01 Autenticacao e acesso

O sistema deve permitir cadastro, login, renovacao de sessao e encerramento de sessao. Cada usuario deve acessar apenas as propriedades e dispositivos aos quais esta associado.

### RF02 Cadastro de propriedade

O usuario deve cadastrar uma propriedade com nome, endereco opcional, fuso horario, unidade de volume e limiar de notificacao. Uma propriedade pode possuir varios dispositivos.

### RF03 Cadastro e vinculacao de dispositivo

O usuario deve registrar um dispositivo ESP32, associar um medidor e consultar seu ultimo heartbeat, estado de conectividade e ultima leitura recebida.

### RF04 Ingestao de telemetria

O dispositivo deve enviar leituras com identificador unico, timestamp UTC, volume acumulado ou vazao instantanea, unidade e metadados opcionais. Reenvios do mesmo evento nao podem duplicar o consumo.

### RF05 Consulta e agregacao

O usuario deve consultar consumo por hora, dia, mes, periodo customizado e comparacao com periodo anterior equivalente.

### RF06 Deteccao de anomalias

O sistema deve executar detectores habilitados para o dispositivo ou propriedade, armazenando pontuacao, severidade, explicacao, janela analisada e evidencias.

### RF07 Alertas

O sistema deve criar alertas para anomalias relevantes, evitar repeticao excessiva, permitir reconhecimento pelo usuario e registrar resolucao ou falso positivo.

### RF08 Dashboard

O painel deve destacar consumo do dia, consumo do periodo, variacao, tendencia, dispositivos offline, alertas abertos e uma visualizacao temporal legivel em celular e desktop.

## 5. Modelo de dominio e dados

### 5.1 Entidades principais

| Entidade | Responsabilidade | Campos essenciais |
|---|---|---|
| User | identidade e acesso | id, email, password_hash, name, status, created_at |
| RefreshToken | renovacao de sessao | id, user_id, token_hash, expires_at, revoked_at |
| Property | unidade monitorada | id, owner_id, name, timezone, volume_unit |
| PropertyMember | acesso compartilhado | property_id, user_id, role |
| Device | ESP32 e credenciais | id, property_id, serial_number, name, status, last_seen_at |
| Meter | medidor logico | id, device_id, model, resolution, installation_date |
| TelemetryReading | evento bruto | id, device_id, event_id, recorded_at, cumulative_volume, flow_rate, quality |
| ConsumptionAggregate | serie agregada | id, property_id, bucket_start, bucket_size, volume, sample_count |
| AnomalyEvent | resultado de detector | id, property_id, device_id, detector_type, score, severity, evidence, detected_at |
| Alert | comunicacao acionavel | id, anomaly_id, status, channel, acknowledged_at, resolved_at |
| NotificationPreference | preferencia do usuario | user_id, property_id, channel, threshold, enabled |
| AuditLog | rastreabilidade | id, actor_id, action, resource_type, resource_id, metadata, created_at |

### 5.2 Regras de persistencia

- Todos os IDs sao UUID.
- Datas de eventos sao armazenadas em UTC com timezone; o fuso da propriedade serve para exibicao e agrupamento.
- `TelemetryReading.event_id` e unico por dispositivo.
- Para leituras de volume acumulado, `delta_volume` e derivado apenas quando a sequencia for valida; reset do medidor gera um marcador de qualidade.
- Volumes nao podem ser negativos. Vazao negativa e rejeitada.
- Agregacoes sao reproduziveis a partir das leituras brutas.
- Exclusao fisica de leituras nao faz parte do fluxo normal; correcao deve gerar evento ou registro de auditoria.
- Indices recomendados: `(device_id, recorded_at)`, `(property_id, bucket_start, bucket_size)`, `(property_id, status, detected_at)` e `(event_id, device_id)`.

### 5.3 Exemplo de SQLAlchemy 2.x

```python
class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(80))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cumulative_volume: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    flow_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    quality: Mapped[str] = mapped_column(String(32), default="valid")

    __table_args__ = (
        UniqueConstraint("device_id", "event_id", name="uq_reading_device_event"),
    )
```

## 6. API REST

### 6.1 Convencoes

- Prefixo: `/api/v1`.
- JSON em todas as requisicoes e respostas.
- Autenticacao de usuario: `Authorization: Bearer <access_token>`.
- Ingestao de dispositivo: `X-Device-Key` ou assinatura HMAC por dispositivo.
- Respostas de colecao usam `items`, `limit`, `cursor` e `has_more`.
- Erros seguem `{"code": "...", "message": "...", "details": {...}}`.
- Timestamps aceitam ISO 8601 e sao normalizados para UTC.
- A API deve emitir OpenAPI e exemplos de payload para o frontend e o firmware.

### 6.2 Endpoints de usuario

| Metodo | Rota | Funcao |
|---|---|---|
| POST | `/auth/register` | cria usuario |
| POST | `/auth/login` | cria sessao |
| POST | `/auth/refresh` | renova access token |
| POST | `/auth/logout` | revoga refresh token |
| GET | `/me` | retorna perfil do usuario |
| PATCH | `/me` | atualiza perfil |

### 6.3 Endpoints de propriedades e dispositivos

| Metodo | Rota | Funcao |
|---|---|---|
| GET | `/properties` | lista propriedades acessiveis |
| POST | `/properties` | cria propriedade |
| GET | `/properties/{property_id}` | detalhes |
| PATCH | `/properties/{property_id}` | atualiza configuracoes |
| DELETE | `/properties/{property_id}` | arquiva propriedade |
| GET | `/properties/{property_id}/members` | lista membros |
| POST | `/properties/{property_id}/members` | adiciona membro |
| GET | `/devices` | lista dispositivos |
| POST | `/devices` | cadastra dispositivo |
| GET | `/devices/{device_id}` | detalhes e status |
| PATCH | `/devices/{device_id}` | renomeia ou configura |
| POST | `/devices/{device_id}/rotate-key` | gira credencial |
| GET | `/devices/{device_id}/health` | heartbeat e qualidade |

### 6.4 Telemetria e consumo

| Metodo | Rota | Funcao |
|---|---|---|
| POST | `/ingestion/telemetry` | recebe uma leitura |
| POST | `/ingestion/telemetry/batch` | recebe lote de leituras |
| GET | `/properties/{property_id}/consumption` | serie agregada |
| GET | `/properties/{property_id}/consumption/summary` | indicadores resumidos |
| GET | `/devices/{device_id}/readings` | leituras brutas com filtros |
| POST | `/properties/{property_id}/aggregates/rebuild` | reprocessa periodo autorizado |

### 6.5 Anomalias, alertas e dashboard

| Metodo | Rota | Funcao |
|---|---|---|
| GET | `/properties/{property_id}/anomalies` | lista anomalias |
| GET | `/anomalies/{anomaly_id}` | detalhes e evidencias |
| GET | `/properties/{property_id}/alerts` | lista alertas |
| POST | `/alerts/{alert_id}/acknowledge` | reconhece alerta |
| POST | `/alerts/{alert_id}/resolve` | resolve alerta |
| POST | `/alerts/{alert_id}/false-positive` | marca falso positivo |
| GET | `/properties/{property_id}/dashboard` | payload pronto para o painel |

### 6.6 Operacao e saude

| Metodo | Rota | Funcao |
|---|---|---|
| GET | `/health/live` | processo responde |
| GET | `/health/ready` | API e banco prontos |
| GET | `/metrics` | metricas para observabilidade |

### 6.7 Payload de ingestao

```json
{
  "device_serial": "ESP32-AGUA-0001",
  "event_id": "00000000-0000-0000-0000-000000000123",
  "recorded_at": "2026-09-22T21:00:00Z",
  "cumulative_volume_liters": 1842.370,
  "flow_rate_liters_minute": 0.420,
  "battery_percent": 87,
  "signal_dbm": -61,
  "firmware_version": "1.2.0"
}
```

Resposta recomendada: `202 Accepted` quando a leitura for aceita, acompanhada de `reading_id`, `duplicate` e `normalized_at`. Reenvio do mesmo `event_id` deve retornar sucesso idempotente, sem novo registro.

## 7. Ingestao de telemetria do ESP32

### 7.1 Fluxo

1. O firmware mede a vazao em intervalo configuravel.
2. O dispositivo calcula ou envia volume acumulado, mantendo o contador local.
3. Cada evento recebe `event_id` unico e timestamp UTC.
4. O ESP32 envia por HTTPS; em caso de falha, armazena uma fila local limitada.
5. A API autentica o dispositivo, valida o schema e aplica idempotencia.
6. A leitura e persistida como dado bruto.
7. Um processo atualiza agregacoes e executa detectores.
8. O painel consulta o estado consolidado.

### 7.2 Resiliencia

- Retry exponencial no dispositivo para erros transitorios.
- Limite de lote para evitar payloads excessivos.
- Aceitacao de leituras atrasadas dentro de uma janela configuravel.
- Separacao entre `recorded_at` e `received_at`.
- Registro de leituras fora de ordem, duplicadas e com salto de contador.
- Dead-letter log para eventos rejeitados, sem descartar o payload original durante a investigacao.

## 8. Agregacoes de consumo

O sistema deve preservar a leitura bruta e produzir agregacoes por hora, dia e mes. O agrupamento usa o fuso da propriedade para definir fronteiras de calendario, mas persiste os instantes com timezone.

### 8.1 Calculo

Para medidor cumulativo, o consumo do intervalo e:

```text
consumo_intervalo = leitura_atual - leitura_anterior
```

Se o contador diminuir, o intervalo recebe qualidade `counter_reset` e nao entra automaticamente no total. Se houver uma lacuna, o sistema indica a ausencia de dados em vez de inventar valores.

### 8.2 Indicadores do dashboard

- consumo no periodo selecionado;
- media diaria e media por hora;
- comparacao com o periodo anterior equivalente;
- maior intervalo de consumo;
- percentual de dados validos;
- tempo desde a ultima leitura;
- numero de anomalias abertas;
- estimativa de consumo continuo fora do horario habitual, quando aplicavel.

## 9. Anomalias e alertas

### 9.1 Contrato de detector

Todo detector implementa um contrato semelhante a:

```python
class AnomalyDetector(Protocol):
    name: str

    async def detect(
        self,
        context: DetectionContext,
    ) -> list[AnomalyCandidate]: ...
```

Cada candidato deve informar `detector_type`, `score`, `severity`, `reason`, `window_start`, `window_end`, `baseline`, `observed_value` e `evidence` serializavel.

### 9.2 Nivel 1 Regras explicaveis

O MVP deve comecar por regras deterministicas, faceis de explicar e auditar:

| Regra | Exemplo de sinal | Severidade inicial |
|---|---|---|
| Fluxo continuo | vazao acima de um minimo por muitas horas | alta |
| Consumo noturno | consumo persistente entre horario configurado | media |
| Salto de consumo | variacao acima do limiar percentual | media |
| Pico impossivel | valor acima do limite fisico do medidor | alta |
| Dispositivo silencioso | nenhuma leitura dentro da janela esperada | media |
| Baixa qualidade | muitos eventos invalidos ou fora de ordem | baixa |

As regras devem permitir configuracao por propriedade e registrar qual limiar foi aplicado.

### 9.3 Nivel 2 Estatistica

Quando houver historico suficiente, usar metodos estatisticos por serie e por horario:

- media movel e desvio padrao robusto;
- z-score com limite configuravel;
- mediana por faixa horaria e dia da semana;
- IQR para reduzir efeito de outliers;
- EWMA para detectar aumento sustentado;
- comparacao com baseline dos ultimos 7, 14 ou 30 dias.

O baseline deve exigir dados minimos e evitar comparar feriados, periodos de ausencia ou falhas do dispositivo como se fossem comportamento normal.

### 9.4 Nivel 3 Machine learning

ML deve ser opcional e posterior ao MVP. Candidatos: Isolation Forest, Local Outlier Factor, autoencoder simples ou modelo de previsao com intervalo de confianca. O modelo nao deve substituir as regras explicaveis.

Requisitos para habilitar ML:

- dataset versionado e com qualidade monitorada;
- separacao entre treino, validacao e teste temporal;
- metricas de precision, recall e taxa de falso positivo;
- explicacao dos sinais que influenciaram a pontuacao;
- fallback para regras quando o modelo estiver indisponivel;
- registro da versao do modelo em cada anomalia.

### 9.5 Severidade e alerta

Uma anomalia vira alerta quando supera o limiar da propriedade ou quando e repetida por uma janela sustentada. A severidade deve combinar score, duracao, volume adicional estimado e confianca.

Estados do alerta: `open`, `acknowledged`, `resolved`, `false_positive`, `suppressed`.

O sistema deve agrupar eventos semelhantes em um alerta para evitar notificacao repetitiva. A mensagem deve dizer o que foi observado, em qual periodo, por que merece atencao e qual verificacao pratica o usuario pode fazer.

## 10. Frontend e experiencia do usuario

### 10.1 Direcao visual

O frontend deve parecer um painel de operacao moderno: fundo neutro, superficies claras, tipografia forte, azul ou turquesa como cor de agua, amarelo para atencao e vermelho apenas para severidade alta. O destaque visual deve ser reservado a mudancas e alertas, nao a decoracao.

### 10.2 Paginas

- **Login:** acesso limpo, validacao clara e estados de erro compreensiveis.
- **Dashboard:** consumo do dia, variacao, serie temporal, alertas abertos e dispositivos.
- **Historico:** filtros de periodo, granularidade e comparacao.
- **Dispositivo:** ultima comunicacao, qualidade, firmware e leituras recentes.
- **Alertas:** fila com filtros por estado e severidade, detalhes e acoes.
- **Configuracoes:** propriedade, membros, limiares e preferencias.

### 10.3 Acessibilidade

Usar componentes semanticos, foco visivel, contraste adequado, textos alternativos, estados nao dependentes apenas de cor e navegacao por teclado. Graficos devem ter resumo textual e tabela de dados sob demanda.

## 11. Estrutura de pastas

```text
agua-monitoramento/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── v1/
│   │   │       ├── auth.py
│   │   │       ├── properties.py
│   │   │       ├── devices.py
│   │   │       ├── telemetry.py
│   │   │       ├── consumption.py
│   │   │       ├── anomalies.py
│   │   │       └── alerts.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── ingestion.py
│   │   │   ├── aggregation.py
│   │   │   └── alerts.py
│   │   ├── detection/
│   │   │   ├── base.py
│   │   │   ├── rules.py
│   │   │   ├── statistical.py
│   │   │   └── ml.py
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── api/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── hooks/
│   ├── schemas/
│   ├── public/
│   ├── tests/
│   └── Dockerfile
├── firmware/
│   ├── src/
│   └── README.md
├── docker-compose.yml
├── .env.example
├── AGENTS.md
└── README.md
```

## 12. Seguranca

- Hash de senha com Argon2id; nunca armazenar senha em texto puro.
- Access token curto e refresh token rotacionado, armazenado apenas como hash.
- Credencial individual por dispositivo, com rotacao e revogacao.
- HTTPS obrigatorio fora do ambiente local.
- Validacao estrita de payloads, limites de tamanho e rate limiting.
- Controle de acesso por propriedade e papel (`owner`, `admin`, `viewer`).
- Segredos somente por variaveis de ambiente ou secret manager.
- Logs sem tokens, senhas ou dados sensiveis.
- Auditoria para alteracoes de limiar, membros, credenciais e resolucao de alertas.
- Backups do PostgreSQL, teste de restauracao e politica de retencao.
- CORS restrito aos dominios autorizados.
- Dependencias fixadas e atualizadas com revisao de seguranca.

## 13. Docker e operacao

### 13.1 Servicos locais

```yaml
services:
  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    depends_on: [db]

  web:
    build: ./frontend
    depends_on: [api]

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: agua
      POSTGRES_USER: agua
      POSTGRES_PASSWORD: local-only

  # Incluir quando a analise sair do request path.
  redis:
    image: redis:7-alpine
```

### 13.2 Comandos de referencia

```text
docker compose up --build
alembic upgrade head
pytest
ruff check .
mypy app
```

Em producao, executar migrations como etapa controlada de deploy, usar imagens imutaveis, healthchecks, limites de memoria e coleta de logs/metricas.

## 14. Testes e qualidade

### Piramide de testes

1. **Unidade:** calculo de delta, regras, severidade, timezone, idempotencia e transicoes de alerta.
2. **Integracao:** SQLAlchemy com PostgreSQL, migrations, repositorios e worker.
3. **API:** autenticacao, autorizacao, schemas, erros e filtros.
4. **Frontend:** componentes, estados de carregamento, validacao e acessibilidade.
5. **E2E:** login, cadastro, ingestao simulada, dashboard e reconhecimento de alerta.

### Cenarios obrigatorios

- reenvio do mesmo evento;
- leituras fora de ordem;
- reset do contador acumulado;
- ausencia de leituras;
- horario de verao ou mudanca de timezone;
- usuario sem acesso a outra propriedade;
- detector sem historico suficiente;
- modelo de ML indisponivel;
- alerta repetido sendo agrupado;
- banco indisponivel e recuperacao do servico.

## 15. AGENTS.md com regras para IA

O arquivo `AGENTS.md` deve ficar na raiz do repositorio e conter as regras abaixo. A versao completa tambem e entregue separadamente junto deste documento.

```markdown
# AGENTS.md

## Objetivo do repositorio

Este repositorio implementa uma plataforma de monitoramento de consumo de agua. A API recebe telemetria, calcula consumo, detecta anomalias e expoe alertas para um dashboard web.

## Regras gerais

1. Leia este arquivo e o README antes de modificar codigo.
2. Preserve a separacao entre API, dominio, persistencia e interface.
3. Nao introduza uma dependencia nova sem justificar o motivo e o impacto.
4. Nao remova dados brutos para corrigir uma agregacao; corrija o processamento e registre a mudanca.
5. Toda alteracao de schema deve vir com migration Alembic reversivel quando possivel.
6. Toda rota nova deve ter schema Pydantic, autorizacao, teste e documentacao OpenAPI coerente.
7. Leituras de telemetria devem ser idempotentes por dispositivo e event_id.
8. Nunca diga que o sistema localizou fisicamente um vazamento; use a linguagem de anomalia ou comportamento compativel com vazamento.
9. Regras de deteccao devem ser explicaveis e manter a evidencia usada no resultado.
10. Modelos de ML sao opcionais: sempre forneca fallback por regras e registre a versao do modelo.

## Backend

- Use SQLAlchemy 2.x com typing e async quando o modulo ja for assincrono.
- Nao coloque regra de negocio em endpoint; use servicos ou casos de uso.
- Valide limites, unidades, timezone e ownership.
- Nao exponha entidades ORM diretamente como resposta publica.
- Use transacoes explicitas nos fluxos de ingestao e escrita.

## Frontend

- Use TypeScript estrito.
- Reutilize componentes shadcn/ui antes de criar componentes visuais duplicados.
- Trate loading, erro, vazio e sucesso.
- Nao use cor como unico indicador de severidade.
- Mantenha graficos legiveis em telas pequenas e ofereca resumo textual.

## Testes e verificacao

- Execute testes relacionados antes de concluir.
- Para mudancas de API, rode testes de contrato e de autorizacao.
- Para mudancas de deteccao, inclua exemplos normais, anomalos e dados insuficientes.
- Para mudancas de frontend, verifique estados de carregamento e acessibilidade.
- Nao declare que um teste passou sem executa-lo.

## Seguranca e dados

- Nao registre tokens, senhas, chaves de dispositivo ou payloads sensiveis.
- Nao use credenciais reais em testes.
- Nao altere permissao de outro usuario para fazer um teste passar.
- Prefira operacoes reversiveis e preserve a auditoria.

## Comunicacao da mudanca

Ao finalizar, informe: resumo, arquivos alterados, testes executados, migrations criadas, riscos conhecidos e proximo passo recomendado.
```

## 16. Roadmap

### Fase 0 Preparacao

- fechar unidades, fuso, precisao e contrato de telemetria;
- criar repositorio, Docker Compose, CI e ambientes;
- definir design tokens e wireframes do dashboard.

### Fase 1 MVP operacional

- autenticacao e propriedades;
- dispositivos e credenciais;
- ingestao idempotente;
- agregacoes horarias e diarias;
- regras de fluxo continuo, consumo noturno e dispositivo offline;
- alertas no dashboard;
- testes e observabilidade basica.

### Fase 2 Produto utilizavel

- membros e papeis;
- notificacoes por e-mail ou push;
- filtros e comparativos avancados;
- reprocessamento controlado;
- estatistica robusta e baseline por faixa horaria;
- exportacao CSV.

### Fase 3 Escala e inteligencia

- worker dedicado, Redis e filas;
- particionamento ou hypertables se o volume justificar;
- modelos ML versionados;
- explicabilidade e monitoramento de drift;
- previsao de consumo e recomendacoes personalizadas.

### Criterios de pronto do MVP

- Uma leitura pode ser enviada pelo ESP32 e aparece no dashboard sem duplicacao.
- O usuario consegue consultar consumo horario e diario.
- Uma anomalia sustentada gera alerta com explicacao.
- O usuario consegue reconhecer e resolver ou marcar falso positivo.
- Migrations, testes, logs e healthchecks funcionam em ambiente Docker limpo.
- Um agente de IA consegue contribuir seguindo o `AGENTS.md` sem quebrar isolamento, seguranca ou rastreabilidade.

## 17. Valor entregue

Transformar dados de consumo de agua em informacoes claras e uteis, permitindo que o usuario acompanhe melhor seu consumo, compreenda alteracoes no comportamento habitual e perceba possiveis anomalias com maior antecedencia. Dessa forma, a solucao apoia decisoes mais rapidas, reduz desperdicios e contribui para um uso mais consciente da agua.
