# Instruções do AquaFlow

## Contexto e fontes

O AquaFlow monitora o consumo de água: recebe telemetria de dispositivos, calcula consumo, identifica anomalias explicáveis e apresenta alertas para acompanhamento. O sistema sinaliza comportamentos que merecem verificação; não afirma localizar fisicamente um vazamento.

Antes de alterar o projeto, leia este arquivo, o [README](README.md) e a [especificação do produto e da API](especificacao-monitoramento-consumo-agua.md). A especificação é a referência para requisitos funcionais, contratos e stack. Se o código existente parecer divergir dela, identifique a divergência e proponha como resolvê-la; não mude silenciosamente o comportamento esperado nem a especificação.

As regras deste arquivo valem para todo o repositório. Para trabalho no backend ou na API, leia também [docs/agents/api.md](docs/agents/api.md). Essa orientação detalha como aplicar a especificação, sem substituí-la.

## Como trabalhar

- Preserve os limites entre interface HTTP, domínio, persistência e apresentação. Mantenha o padrão existente quando ele respeitar esses limites.
- Implemente somente o escopo pedido, em mudanças pequenas e verificáveis. Não crie estrutura, endpoints ou funcionalidades fora do escopo sem necessidade justificada.
- Antes de adicionar uma dependência, explique a necessidade e o impacto. Prefira as tecnologias já definidas na especificação.
- Quando faltar uma decisão de produto, segurança ou tratamento de dados, apresente a lacuna e pergunte antes de fixar o comportamento. Para escolhas técnicas reversíveis, escolha uma opção coerente, registre a suposição e siga em frente.
- Não apague telemetria bruta para corrigir agregações. Corrija o processamento e preserve a rastreabilidade.
- Mudanças de schema devem incluir migration Alembic reversível quando possível.
- Não exponha entidades ORM como respostas públicas. Valide limites, unidades, timezone e acesso ao recurso.
- Regras de detecção devem explicar o resultado e preservar as evidências usadas. Mantenha os detectores por regras como fallback; na entrega ampliada, versione os modelos e registre qual modelo produziu cada inferência.

## Skills do projeto

As skills disponíveis ficam em `.agents/skills/`. Leia e siga a skill pertinente quando a tarefa corresponder ao seu propósito; não carregue skills sem relação com o trabalho.

- `tdd`: implementar uma funcionalidade ou correção com ciclo de testes.
- `diagnosing-bugs`: investigar uma falha ou regressão difícil.
- `codebase-design`: decidir interfaces e limites entre módulos.
- `domain-modeling`: esclarecer termos do domínio ou registrar decisões de domínio.
- `grill-with-docs`: alinhar uma decisão de produto ou arquitetura e documentar os termos e decisões que surgirem.
- `code-review`: revisar uma mudança ou branch quando solicitado.
- `research`: verificar comportamento de tecnologias e documentação oficial quando necessário.

## Interface e frontend

- Use TypeScript estrito onde o frontend estiver implementado.
- Reutilize componentes shadcn/ui existentes antes de criar componentes visuais equivalentes.
- Cubra estados de carregamento, erro, vazio e sucesso.
- Não use cor como único indicador de severidade. Mantenha gráficos legíveis em telas pequenas e forneça um resumo textual.

## Segurança, dados e verificação

- Não registre tokens, senhas, chaves de dispositivo ou payloads sensíveis. Não use credenciais reais em testes.
- Não altere permissões de outro usuário para fazer um teste passar. Preserve isolamento por usuário e propriedade e mantenha a auditoria.
- Execute os testes relacionados às mudanças. Para alterações de API, verifique contratos e autorização; para detecção, cubra casos normais, anômalos e dados insuficientes; para frontend, verifique estados e acessibilidade.
- Nunca declare que uma verificação passou sem executá-la. Se não puder executá-la, diga o que faltou e qual risco isso deixa.

## Ao concluir

Resuma o que mudou e por quê. Informe arquivos alterados, verificações executadas, migrations, riscos conhecidos e próximo passo recomendado. Não diga que o sistema localizou um vazamento; use “anomalia” ou “comportamento compatível com vazamento”.
