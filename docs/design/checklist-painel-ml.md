# Modelos e treinamento

Branch: `feat/painel-ml`.

## Proposta visual

- [x] Inspecionar fundamentos, componentes e telas existentes no Figma.
- [x] Criar prancha desktop editável com a identidade atual do AquaFlow.
- [x] Exibir modelo ativo, versão, data de treinamento e estado do worker.
- [x] Mostrar AP, precisão, recall e F1 com conjunto e limiar identificados.
- [x] Comparar KNN, Árvore de Decisão, Random Forest e baseline.
- [x] Desenhar matriz de confusão e curva precisão-recall; oferecer ROC complementar.
- [x] Mostrar treino e validação por fold, dispersão e resultados de estresse.
- [x] Desenhar os controles de execução e conjunto avaliado e explicar o critério de seleção.
- [x] Apresentar histórico de execuções e detalhe do treinamento.
- [x] Planejar estados de carregamento, erro, vazio e serviço indisponível.
- [x] Adaptar a proposta para mobile e tema escuro.
- [x] Conferir legibilidade, alinhamento e textos na exportação desktop; auditoria sem avisos de overflow.

## Integração e implementação

- [x] Mapear relatórios e dados do MLflow para o contrato da API.
- [x] Distinguir o modelo ativo dos candidatos de treinamento.
- [x] Disponibilizar consultas de execuções, avaliações e estado do worker pela API autenticada.
- [x] Implementar a navegação para a área técnica e os componentes visuais.
- [x] Integrar métricas e gráficos aos relatórios das execuções. Atualizar pela API ao mudar a execução ou o modelo ativo; não fixar números do protótipo no frontend.
- [x] Apresentar hiperparâmetros, atributos, amostras, períodos e origem dos dados no detalhe.
- [x] Identificar as avaliações com série híbrida e cenários simulados.
- [x] Validar contrato, autenticação, estados e acessibilidade básica dos controles e gráficos.
- [x] Conferir a implementação no Docker e o endpoint com execuções reais do MLflow local.
- [x] Registrar implementação e limites conhecidos para o critério 11.

A tela consulta `GET /api/v1/ml/training-dashboard`, protegida por autenticação. O
contrato inclui modelo ativo, histórico de execuções, relatório selecionado e
estado do worker de inferência. O artefato ativo é validado pelo SHA-256; relatórios
históricos são lidos do volume local do MLflow em modo somente leitura. Quando um
relatório antigo não contém curvas ou folds, a interface informa que esses dados
não foram registrados naquela execução.

O painel e as rotas de treinamento são restritos ao e-mail configurado em
`ROOT_USER_EMAIL`. O cadastro público não concede o papel e também não pode
reservar esse e-mail. Contas comuns recebem `403`; quando a configuração está
vazia, o acesso administrativo fica desativado.

Verificações executadas em 20/11/2026: backend `42 passed, 3 skipped`, testes do
treinamento `3 passed`, frontend `3 passed`, typecheck, lint, build Next.js e
Compose com API e frontend saudáveis. Smoke test autenticado local: modelo `knn`,
três execuções, curvas de teste/estresse, três folds, histórico `200`, execução
inexistente `404` e acesso anônimo `401`.

## Escopo posterior

- Telemetria e inferências ao vivo em uma entrega própria; esta tela não conclui sozinha essa parte do critério 11.

## Estado do Figma

Em 20/11/2026, o plugin conectou e permitiu criar a seção `38:363` e a prancha
`38:364` (31 · Modelos e treinamento), com navegação original reutilizada,
cabeçalho, modelo ativo, métricas e comparação de modelos. Os números são da
execução de referência; a aplicação deve consultar dados dinamicamente.

A conexão foi restabelecida e a mesma prancha foi completada com matriz de
confusão, barras de AP por conjunto, médias de treino e validação, dispersão,
histórico e configuração. Exportação desktop inspecionada visualmente e auditoria
de texto com zero avisos após ajuste de largura do cabeçalho Situação.
Foram acrescentados os controles de execução/conjunto, o critério de seleção,
curvas PR/ROC e resultados dos três folds do KNN. Curvas e folds foram
recalculados com o artefato ativo e a série preparada, com hash de dados
conferido. AUC ROC: 0,998813; AP de validação por fold: 0,943507,
0,977447 e 0,979592. Os gráficos no Figma são elementos nativos editáveis.

Pranchas complementares:

- `40:955`: 32 · Modelos e treinamento / Dark.
- `40:1323`: 33 · Mobile / Modelos e treinamento.
- `40:1297`: 34 · Modelos e treinamento / Estados.

As quatro pranchas foram exportadas e inspecionadas; as auditorias de texto
retornaram zero avisos. O estado de navegação inativa no tema escuro foi
corrigido após a inspeção. A seção desktop não colide com outras seções.
As interações dos seletores são uma referência visual, ainda sem navegação
interativa configurada no Figma. A interface e a consulta dinâmica estão
implementadas. Desde 20/11/2026, o controle de acesso administrativo e o
acionamento seguro de retreinamento também estão implementados; confira a seção
de retreinamento local no todo.

## Fluxos de navegação em preparação

Foram desenhados os destinos na seção `42:1961`:

- `42:1962`: 35 · Selecionar execução.
- `42:1969`: 36 · Selecionar conjunto.
- `42:1978`: 37 · Detalhes do treinamento.
- `42:2002`: 38 · Avaliação de estresse, com métricas do artefato validado.

- [ ] Ligar Alterar execução (`40:1321`) ao seletor `42:1962` como overlay.
- [ ] Ligar Alterar conjunto (`40:1322`) ao seletor `42:1969` como overlay.
- [ ] Ligar a linha da execução (`42:1965`) ao painel principal.
- [ ] Ligar teste (`42:1971`) ao painel principal e estresse (`42:1974`) à avaliação de estresse.
- [ ] Ligar Cancelar dos seletores ao fechamento do overlay.
- [ ] Ligar detalhes (`39:397`, `40:521`) ao destino `42:1978`.
- [ ] Ligar retornos (`42:1979`, `42:2003`) ao painel principal.
- [ ] Verificar todos os caminhos no modo de apresentação.

A conexão oficial do Figma exige reautenticação. O bridge local disponível
não expõe escrita de reactions. A tentativa pela interface criou uma interação
sem destino em `40:1322` (Click None); o destino não foi confirmado. A automação
do editor apresentou erros de janela minimizada e geometria indisponível.
Não considerar os fluxos clicáveis concluídos.

Exportações em `C:/Users/guivr/Pictures/Figma MCP Exports/`, com prefixos
`31-Modelos-e-treinamento`, `32-Modelos-e-treinamento-Dark`,
`33-Mobile-Modelos-e-treinamento` e `34-Modelos-e-treinamento-Estados`.

Conjunto organizado para implementação salvo em
`C:/Users/guivr/Pictures/Figma MCP Exports/Painel ML/`: oito PNGs, de 31 a 38,
com nomes estáveis e resolução original, exportados novamente em 20/11/2026.
Inclui desktop, dark, mobile, estados, seletores, detalhes e estresse. As imagens
35 a 38 foram também inspecionadas visualmente após esta exportação.

## Acesso administrativo

A API do painel exige a conta identificada por ROOT_USER_EMAIL, configurado no ambiente com o e-mail da conta root existente. Vazio desativa o acesso. Cadastro público não concede privilégios. Contas comuns recebem 403. A consulta auth/me informa is_admin para controlar a navegação. Ao recriar o banco, configure novamente o UUID da conta root.
