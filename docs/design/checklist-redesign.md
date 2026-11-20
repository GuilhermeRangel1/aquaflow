# Checklist do redesign AquaFlow

Referência: 32 pranchas do protótipo V2 exportadas pelo Figma Local Bridge.
As pranchas documentam telas, estados e referências. Na lista abaixo, [x] significa que existe
uma implementação correspondente no código; a comparação visual é acompanhada na seção própria.
Fundamentos, guia e biblioteca são referências para componentes compartilhados.

Os checkboxes desta lista indicam que existe um **fluxo ou estado correspondente no código**.
Eles não garantem que todos os detalhes estejam implementados, que o layout seja igual ao Figma
ou que a tela tenha sido conferida visualmente. A comparação visual é acompanhada separadamente
abaixo.

- [x] 00 · Fundamentos · tokens e estilos compartilhados
- [x] 01 · Entrar
- [x] 02 · Criar conta
- [x] 03 · Visão geral
- [x] 04 · Medidores
- [x] 05 · Detalhe do medidor
- [x] 06 · Alertas
- [x] 07 · Detalhe do alerta
- [x] 08 · Configurações
- [x] 09 · Configurações de outra propriedade · mesma tela com outra propriedade selecionada
- [x] 10 · Adicionar propriedade
- [x] 11 · Arquivar propriedade · diálogo de confirmação
- [x] 12 · Trocar propriedade · seletor da propriedade
- [x] 13 · Propriedade arquivada · confirmação e retorno à visão geral, sem página separada
- [x] 14 · Primeira propriedade
- [x] 15 · Falha de carregamento
- [x] 16 · Sem leituras
- [x] 17 · Mobile · Visão geral · layout responsivo
- [x] 18 · Mobile · Medidores · layout responsivo
- [x] 19 · Mobile · Alertas · layout responsivo
- [x] 20 · Mobile · Configurações · layout responsivo
- [x] 21 · Mobile · Entrar · layout responsivo
- [x] 22 · Mobile · Arquivar · diálogo responsivo
- [x] 23 · Tema escuro · Visão geral
- [x] 24 · Tema escuro · Configurações
- [x] 25 · Tema escuro · Entrar
- [x] 26 · Estados e componentes compartilhados
- [x] 27 · Guia de navegação · navegação implementada no shell; prancha é referência, não página
- [x] 28 · Enviando login
- [x] 29 · Enviando cadastro
- [x] 30 · Erro de autenticação
- Biblioteca · catálogo visual de componentes · referência do Figma, sem tela ou rota própria na aplicação

## Andamento

- [x] Exportar as 32 pranchas originais.
- [x] Ajustar a proporção da barra lateral e os espaçamentos compartilhados no desktop.
- [x] Implementar e conferir as cinco primeiras telas de produto no Docker: login, cadastro, visão geral, lista e detalhe do medidor.
- [x] Conferir dados híbridos na visão geral e leituras reais do medidor no gráfico de detalhe.
- [ ] Comparar o layout compartilhado renderizado com as pranchas desktop e mobile.
- [ ] Conferir no mobile e no tema escuro as cinco telas implementadas.
- [x] Implementar as telas restantes e seus estados descritos abaixo.

## Andamento técnico · 20/11/2026

### Implementado no código

- [x] Alertas: lista com filtros funcionais, contagens, severidade/estado, medidor, horário e retorno quando não há resultados.
- [x] Detalhe do alerta: motivo, estado, prioridade, evidências expansíveis e ações existentes.
- [x] Configurações: campos agrupados, estados de salvamento/erro e proteção da Casa da Administração.
- [x] Propriedades: criação em tela própria, cancelamento, seleção no seletor, confirmação de arquivamento, carregamento e retorno após arquivar com histórico preservado.
- [x] Primeira propriedade: formulário de início separado de erro de carregamento, com retry no estado de falha.
- [x] Sem medidores/leituras: estado de início com ação para adicionar medidor; leitura ausente em medidor cadastrado explica que os dados ainda estão chegando.
- [x] Mobile e tema escuro: telas reutilizam o shell responsivo e os tokens de tema existentes; o modal usa o diálogo nativo acessível.
- [x] Autenticação: estados de envio e erro já existentes mantidos; movimento reduzido continua respeitado.
- [x] Fundamentos, navegação e componentes: tokens de cores, tipografia, espaçamento, marca, seletor, métricas, avisos, painel de carregamento e componentes de configuração compartilhados.

### Conferência visual ainda pendente

As listas de Medidores e Alertas (04 e 06) foram comparadas com as exportações do Figma
em 1440 × 1080 e conferidas no navegador em 390 × 844. A conta de apresentação tem um
medidor e dois avisos. Os nomes, os horários e o número de itens vêm da API.

- [ ] Comparar as pranchas de produto com as telas renderizadas em desktop, mobile e tema escuro.
- [ ] Conferir visualmente os estados de primeira propriedade, erro inicial de carregamento e casa sem medidores em uma sessão isolada.
- [ ] Conferir arquivamento completo em uma propriedade de teste, sem arquivar a Casa da Administração nem alterar os dados da apresentação.

### Verificações desta rodada

- [x] `npm run format:check`, `npm run lint`, `npm run typecheck` e `npm run build` passaram.
- [x] Imagem do frontend reconstruída e contêiner saudável em `http://localhost:3000`.
- [x] API, PostgreSQL, inferência ML e MQTT continuam saudáveis; contêineres órfãos de validação do PR1 foram removidos.
- [ ] Capturas comparativas automatizadas no navegador: não concluídas; a tentativa de automação local foi bloqueada pela política do ambiente.
- [x] Testes automatizados do frontend: 3 passaram. O teste do seed não iniciou porque o ambiente Python local não tem `asyncpg` instalado.
