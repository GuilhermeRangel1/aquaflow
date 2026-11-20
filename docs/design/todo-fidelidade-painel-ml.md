# Modelos e treinamento — implementação e fidelidade

Atualizado em 20/11/2026. Branch: `feat/painel-ml`.

Este checklist guia a revisão da tela atual. **Implementado não significa visualmente conferido.** Marcar a fidelidade somente depois de comparar a aplicação renderizada com a exportação correspondente.

## Referências

- Código: `frontend/src/app/dashboard/ml-training.tsx` e estilos em `frontend/src/app/globals.css`.
- API: `GET /api/v1/ml/training-dashboard`.
- Protótipos: `C:/Users/guivr/Pictures/Figma MCP Exports/Painel ML/`, imagens 31 a 38.
- Histórico do trabalho: [checklist-painel-ml.md](checklist-painel-ml.md). As marcações antigas de conclusão não comprovam fidelidade visual.

## O que existe e o que deveria existir

| Parte | Estado atual no código | Alvo do protótipo / pendência |
| --- | --- | --- |
| Cabeçalho e navegação | Área de treinamento integrada ao dashboard | Conferir texto, posição, tipografia e estado ativo da área técnica |
| Seleção da execução | Select nativo com data e modelo | Card com execução consultada e ação Alterar; seletor da prancha 35 |
| Seleção do conjunto | Botões Teste e Estresse | Card com conjunto avaliado e ação Alterar; seletor da prancha 36 |
| Modelo em operação | Modelo selecionado, versão ativa, data e worker | Separar claramente execução consultada e modelo ativo; conferir apresentação de parâmetros e acesso aos detalhes |
| Métricas | AP, precisão, recall e F1 dinâmicos | Descrições individuais; precisão e recall em porcentagem; contexto de amostras e limiar |
| Comparação | Tabela de AP, precisão, recall e F1 do conjunto selecionado | AP teste, AP estresse, recall estresse e situação de cada modelo, lado a lado |
| Matriz de confusão | Matriz dinâmica com eixos | Conferir rótulos, descrições das quatro células, dimensões e alinhamento |
| Desempenho por conjunto | Gráfico de AP do conjunto selecionado | Duas barras por modelo: teste cronológico e estresse, com legenda e valores |
| Estabilidade e generalização | Diagnóstico do modelo selecionado | Comparar treino, validação, gap e dispersão de todos os candidatos conforme a referência |
| Histórico | Lista de execuções com seleção por clique | Conferir colunas, identificação legível, estado e acesso ao detalhe |
| Dados e configuração | Amostras, divisão, seleção, hash, parâmetros e atributos | Parâmetros legíveis em vez de JSON bruto; períodos e origem; detalhe da prancha 37 |
| Curvas PR e ROC | Gráficos dinâmicos e mensagem quando ausentes | Conferir geometria, eixos, escala, legenda e ordem das seções |
| Validação por fold | Barras de treino e validação | Valores exatos por fold e resumo de média, desvio e gap |
| Motivo da seleção | Critério e pontuações presentes | Traduzir identificadores técnicos para texto claro e conferir explicação dos conjuntos usados |
| Avaliação de estresse | Troca do conjunto na tela | Conferir conteúdo e contexto da prancha 38 |
| Estados | Carregamento, erro, vazio e histórico indisponível | Comparar com prancha 34; conferir atualização sem apagar dados válidos |
| Mobile e dark | CSS responsivo e tokens de tema | Comparação visual pendente com pranchas 33 e 32 |

## Ordem de execução

### 1. Integridade das informações

- [ ] Conferir cada campo exibido contra o contrato e o relatório real da execução.
- [x] Identificar separadamente modelo ativo, candidato selecionado e execução histórica.
- [x] Evitar apresentar ausência de métrica como zero.
- [x] Exibir teste e estresse simultaneamente na comparação e no gráfico por conjunto.
- [x] Acrescentar resumo de generalização dos candidatos.
- [ ] Apresentar hiperparâmetros com nomes e unidades legíveis.
- [ ] Conferir períodos de treino, validação e teste; corrigir rótulos que não correspondam ao campo.
- [ ] Completar descrições das métricas e formatação percentual.
- [x] Conferir histórico e detalhe do treinamento com a prancha 37.
- [ ] Completar contexto dos folds e motivo da seleção sem fixar números do Figma.

### 2. Estrutura e visual desktop

- [x] Reproduzir os dois cards de seleção e os respectivos seletores.
- [ ] Ajustar o card do modelo em operação e a ação de detalhes.
- [ ] Reproduzir a ordem: comparação → matriz/desempenho → estabilidade → histórico → configuração → curvas → folds → seleção.
- [ ] Conferir largura do conteúdo, altura dos cards, espaçamento, raios e tipografia na mesma largura da referência.
- [ ] Conferir tabela, destaque do modelo ativo, legendas, eixos e tooltips.
- [ ] Revisar estilos acumulados e consolidar regras após estabilizar o layout.

### 3. Mobile, dark e estados

- [ ] Comparar mobile com a prancha 33, incluindo tabelas e seletores.
- [ ] Comparar dark com a prancha 32, incluindo contraste dos gráficos.
- [ ] Comparar carregamento, erro e vazio com a prancha 34.
- [ ] Verificar teclado, foco visível, nomes dos controles e resumo textual dos gráficos.
- [ ] Conferir seleção de execução, troca de conjunto, atualização e retorno dos detalhes.

### 4. Validação final

- [x] Typecheck, lint e build passaram após os ajustes visuais iniciais de 20/11.
- [ ] Executar verificações novamente após completar as pendências.
- [ ] Atualizar o Docker com a versão final.
- [ ] Capturar desktop, mobile e dark da aplicação e comparar com os PNGs.
- [ ] Registrar diferenças restantes e só então marcar a fidelidade como concluída.

## Fora desta revisão visual

- Restrição por papel administrativo: pendente, conforme escopo anterior.
- Disparo de treinamento pela interface: evolução posterior.
- Telemetria e inferências ao vivo: entrega própria.
- Validação residencial real: as métricas atuais usam série híbrida e cenários simulados; não comprovam desempenho em instalações reais.

## Revisão implementada em 20/11

Comparação simultânea de teste/estresse, barras por conjunto, resumo dos candidatos, descrições das células da matriz, percentuais de precisão/recall e correção do rótulo de início do teste implementados. Ausências na comparação aparecem como traço. Lint, TypeScript, três testes do frontend e build Docker passaram. Docker atualizado. A conferência visual e os seletores/detalhes conforme as pranchas continuam pendentes; não considerar a revisão completa.

## Rodada de conclusão

Implementados cards de execução/conjunto e diálogos com seleção, cancelamento, foco nativo e Escape; detalhe da execução com parâmetros, períodos e hash; identificação do modelo em operação separada do relatório consultado; proteção contra respostas fora de ordem; histórico antes da configuração; descrições individuais das métricas; tradução do critério de seleção e atributos com unidades. Baseline consulta os resultados de teste/estresse registrados no relatório, sem inventar valores.

Conferência no navegador: painel dark carregado com dados reais da API, seleção de estresse atualizando métricas e matriz, diálogo de detalhes exibindo execução e períodos. Lint, TypeScript e três testes existentes do frontend passaram. Esses três testes cobrem navegação do dashboard; não constituem testes automatizados dos diálogos.

Ainda pendente: comparação visual completa de mobile e dark com as exportações; estados de erro/vazio exercitados visualmente; consolidação dos estilos acumulados; resumo numérico dos folds fora do tooltip; conferir a fidelidade do detalhe completo com todas as informações da prancha 37. Não marcar fidelidade integral antes dessas conferências.

## Verificação adicional

Detalhe ampliado com busca, seed, combinações, ajustes, folds, gap, partições e hashes implementado e conferido no navegador. Corrigidos fundo transparente e abertura no final do diálogo. Valores exatos dos folds e resumo de média/desvio/gap presentes fora do tooltip. Mobile claro e dark inspecionados a 390 px, sem overflow horizontal da página. Build Docker, lint e TypeScript passaram após a correção final; quality gate completo passou antes dessa correção de apresentação.

Pendência de validação: estados de erro/vazio não foram forçados visualmente nesta rodada; a comparação integral com todas as pranchas e a consolidação dos estilos continuam abertas. Esses itens não impedem o uso local, mas impedem afirmar equivalência visual integral ao Figma.

## Retreinamento pela interface — decisão confirmada

Em 20/11/2026, o usuário escolheu ativar automaticamente o novo modelo após aprovação. O botão de retreinamento ainda não está implementado. A implementação deve executar o pipeline, mostrar progresso/erro, impedir execuções duplicadas e só promover o artefato após as validações; não substituir o modelo ativo no início do treinamento. Relatórios históricos não devem ser sobrescritos.

Correção dos históricos: o contrato agora inclui o relatório ativo separado do relatório consultado. A explicação da seleção permanece vinculada ao modelo ativo. As duas execuções de Random Forest de 19/11 não têm folds nem curvas nos artefatos originais; a interface informa a ausência e reduz o espaço vazio. Quality gate completo aprovado para essa alteração.


## Retreinamento local concluido (20/11/2026)

- O painel oferece Treinar novamente, bloqueia acionamentos simultaneos e mostra estado, falha e conclusao.
- API autoriza o fluxo somente para ROOT_USER_EMAIL; o trabalhador de ML fica interno ao Compose.
- Cadastro público rejeita o e-mail reservado ao root; preencher esse endereço sozinho não concede acesso administrativo.
- Treinamento grava em pasta de candidato; valida hash, AP e comparacao sem regressao de AP/recall nos conjuntos de teste e estresse antes de trocar atomicamente active-model.json.
- O worker consulta o ponteiro ativo e recarrega um artefato novo validado, sem parar as inferencias durante o treinamento.
- Validado no Docker com execucoes aprovadas, historico atualizado, conta comum bloqueada (403) e worker healthy. As execucoes geraram o mesmo hash por usarem o mesmo dataset fixo e seed; os novos registros entraram no historico, mas os pesos nao mudaram.
- A tela desktop foi inspecionada no navegador. Comparacao visual integral de mobile, tema escuro e estados com as exportacoes ainda pendente.
