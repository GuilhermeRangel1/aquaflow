# Orientações para desenvolver a API

Este documento orienta agentes Codex em tarefas do backend. Ele complementa o [AGENTS.md da raiz](../../AGENTS.md); não redefine requisitos do produto. Use a [especificação do AquaFlow](../../especificacao-monitoramento-consumo-agua.md) como referência funcional, de contratos REST e de stack.

## Escopo e precedência

- O objetivo do backend é cobrir a API do MVP descrita na especificação, entregue em fatias pequenas. Uma tarefa não precisa implementar o MVP inteiro.
- A especificação define o comportamento esperado e a stack prevista. O código existente define os padrões locais de organização quando eles não contradizem esse comportamento.
- Se encontrar conflito entre especificação e código, descreva o conflito e proponha a resolução antes de alterar contratos ou comportamento. Não atualize a especificação silenciosamente.
- Se uma lacuna mudar comportamento de produto, autorização, retenção ou interpretação de dados, pergunte antes de escolher. Para uma escolha técnica reversível, adote a opção mais simples compatível, registre a suposição na entrega e evite dependências desnecessárias.
- Não invente requisitos, estados, permissões, códigos de erro ou formatos de payload que não estejam na especificação ou no código existente. Quando forem necessários e estiverem indefinidos, explicite a decisão pendente.
- A especificação está organizada por requisitos e endpoints; consulte suas seções relevantes em vez de copiar listas e contratos para este guia. Se uma decisão precisar mudar, proponha primeiro a alteração da especificação.

## Descoberta antes da implementação

Antes de escolher caminhos ou criar arquivos:

1. Inspecione a estrutura existente, dependências, configuração, migrations e testes.
2. Identifique o comportamento já implementado e as convenções do módulo relacionado.
3. Leia os requisitos e endpoints pertinentes na especificação.
4. Escolha a menor fatia vertical que entregue comportamento observável e testável.

Não presuma uma estrutura de pastas antes de verificar o repositório. Se ainda não houver convenção de backend, proponha uma organização modular simples e coerente com a especificação, sem separar o MVP em serviços distribuídos.

## Limites entre módulos

- **Rotas FastAPI:** traduzem HTTP para comandos/consultas, aplicam dependências de autenticação e autorização e retornam schemas públicos. Não concentram cálculos ou regras de domínio.
- **Schemas Pydantic v2:** validam entradas e definem respostas públicas. Não reutilize modelos ORM como contratos da API.
- **Domínio e casos de uso:** concentram validações e regras de negócio, como idempotência, cálculo de consumo, detecção e transições de alerta.
- **Persistência:** usa SQLAlchemy 2.x e PostgreSQL. Mantenha queries e mapeamentos nos módulos de persistência e use migrations Alembic para evolução de schema.
- **Transações:** delimite explicitamente operações de escrita, especialmente ingestão e fluxos que alteram mais de um registro.
- Use async quando o módulo e as dependências existentes forem assíncronos; não introduza uma segunda abordagem de I/O sem motivo concreto.

## Invariantes da API e dos dados

- Preserve os contratos da especificação: prefixo `/api/v1`, JSON, timestamps normalizados para UTC, paginação de coleções e formato padronizado de erro.
- Toda rota nova precisa de schema de entrada/saída, autorização adequada, documentação OpenAPI coerente e testes de contrato e acesso.
- Confira o ownership em toda leitura ou escrita de propriedade, dispositivo e recurso associado. Uma identidade autenticada não implica acesso a qualquer propriedade.
- Mantenha telemetria idempotente pela combinação dispositivo e `event_id`. Um reenvio não pode duplicar leitura ou consumo.
- Preserve leituras brutas. Derive consumo a partir de leituras válidas; registre resets, lacunas e dados fora de ordem conforme a especificação. Não invente consumo para preencher dados ausentes.
- Valide valores, unidades, limites e timezone na fronteira adequada. Volumes negativos e vazões negativas seguem as restrições da especificação.
- Agregações devem poder ser reproduzidas a partir dos dados brutos. Reprocessamentos devem ser autorizados, rastreáveis e não apagar a fonte de verdade.
- Anomalias devem guardar detector, janela, explicação e evidências. Uma anomalia pode motivar alerta, mas não prova nem localiza fisicamente um vazamento.
- Mantenha detecção baseada em regras como fallback. ML não pode ser requisito para o MVP nem ocultar a versão do modelo usada em um resultado.
- Não registre credenciais, chaves ou payloads sensíveis. Use segredos de ambiente e dados sintéticos nos testes.

### Decisões de segurança que não devem ser presumidas

Decisões aprovadas para este MVP:

- Dispositivo autentica por chave individual no header `X-Device-Key`; a API armazena somente o hash e deve permitir rotação e revogação.
- Cada propriedade tem um único proprietário nesta fase. Não crie endpoints de compartilhamento ou associação de membros agora.
- Os nomes de papel planejados são proprietário, administrador e visualizador. A associação de vários usuários e a matriz detalhada de permissões ficam para a fase seguinte; até lá, proteja recursos por ownership do proprietário.
- Leituras atrasadas são aceitas por até sete dias por padrão, com possibilidade de configuração por propriedade/dispositivo. Timestamp mais de cinco minutos no futuro é rejeitado.
- Estados de alerta aprovados: aberto, reconhecido, resolvido e falso positivo. Agrupe a mesma regra para o mesmo dispositivo enquanto o alerta estiver aberto ou reconhecido; após resolução ou falso positivo, uma recorrência abre novo alerta.

Não volte a perguntar essas decisões durante a implementação. Se uma mudança de escopo ou a especificação revisada entrar em conflito com elas, descreva o conflito e peça orientação antes de mudar o contrato.

## Sequência sugerida para o MVP

Use esta ordem como guia de dependências, não como um plano rígido. Siga outra ordem quando o estado do código justificar e explique o motivo.

1. **Fundação:** configuração, aplicação FastAPI, PostgreSQL, Alembic, erros comuns e health checks. Implementada; a execução real com PostgreSQL ainda requer Docker ativo.
2. **Identidade e acesso:** autenticação, propriedade, dispositivo, ownership e autorização. Cadastro, login, refresh/logout e provisionamento de propriedade/dispositivo estão implementados; associação de membros permanece fora da fase atual.
3. **Telemetria:** validação, persistência transacional, chave por dispositivo e idempotência. Implementada para ingestão individual e em lote.
4. **Consumo:** agregações horária, diária e mensal com timezone, resets e lacunas explícitos. Implementada para a primeira visualização do dashboard.
5. **Anomalias e alertas:** a primeira regra de fluxo contínuo, evidências persistidas, agrupamento, transições de estado e fila no dashboard estão implementados. Regras noturnas/offline e cobertura de integração PostgreSQL permanecem.
6. **Fechamento operacional:** OpenAPI, Docker, health/readiness, logs seguros e cobertura. O Compose também prepara uma conta local com dados sintéticos; falta validar os containers quando o daemon estiver disponível.

Não implemente itens fora do MVP, como fechamento remoto de válvula, faturamento, integração com concessionárias ou ML decisório, a menos que o usuário altere explicitamente o escopo.

## Verificação

- Para cada fatia, execute testes relacionados e relate os comandos e resultados reais.
- Cubra regras de domínio com testes de unidade; persistência e migrations com testes de integração; rotas com testes de contrato e autorização.
- Inclua cenários de reenvio idempotente, acesso cruzado entre usuários/propriedades, timestamps/timezones, falha de dependência e dados insuficientes quando se aplicarem à mudança.
- Não use credenciais reais nem reduza controles de autorização para facilitar testes.
- Se o ambiente não permitir uma verificação, informe a limitação; não substitua execução por suposição.

## Skills de apoio

Consulte as skills instaladas em `.agents/skills/` quando a tarefa corresponder:

- `tdd` para uma fatia de implementação ou correção;
- `diagnosing-bugs` para falha reproduzível ou regressão difícil;
- `codebase-design` para interfaces e limites entre módulos;
- `domain-modeling` para esclarecer conceitos e linguagem de domínio;
- `grill-with-docs` para decisões ainda ambíguas de produto ou arquitetura;
- `research` para comportamento atual de bibliotecas, protocolos ou documentação oficial;
- `code-review` para revisar uma mudança concluída quando solicitado.

Não use uma skill como substituto da especificação, dos testes ou da confirmação do usuário em decisões de produto e segurança.
