# AquaFlow — Redesign visual e experiência do cliente

> **Objetivo:** transformar o frontend do AquaFlow em uma experiência de produto premium, coesa e memorável — com qualidade visual comparável à de um SaaS comercial maduro — sem comprometer funcionalidades, contratos de API, dados ou comportamento existente.
>
> **Escopo:** frontend / experiência do usuário. Não reescrever backend, API, banco de dados, ingestão MQTT ou regras de negócio para atender a mudanças meramente visuais.

---


## Protótipo de alta fidelidade no Figma

Reconstruído em 19 de novembro de 2026 na conta gvrs@cesar.school a partir das composições e dos componentes da primeira versão. O MCP não oferece duplicação direta entre essas contas. O arquivo anterior foi mantido como referência histórica.

- [Arquivo atual editável](https://www.figma.com/design/Qd38nnUgejHw74QV5gCYAb?node-id=2-75).
- [Fluxo desktop a partir do login](https://www.figma.com/proto/Qd38nnUgejHw74QV5gCYAb?node-id=2-35&starting-point-node-id=2%3A35).
- [Fluxo mobile a partir do login](https://www.figma.com/proto/Qd38nnUgejHw74QV5gCYAb?node-id=3-649&starting-point-node-id=3%3A649).
- [Visão geral escura](https://www.figma.com/design/Qd38nnUgejHw74QV5gCYAb?node-id=2-176).
- [Arquivo anterior](https://www.figma.com/design/qyFZxJkmKnz0M1f1Psjkhg).

### Conteúdo e ajustes aplicados

A versão atual contém 28 pranchas e 182 conexões, com 189 instâncias de componentes e textos editáveis. Os fundamentos e os fluxos da primeira versão foram reconstruídos em operações agrupadas.

- Login e criação de conta.
- Visão geral e gráfico de consumo.
- Medidores e detalhe de leitura.
- Lista e detalhe de alerta.
- Configurações da Casa da Administração e de outra propriedade.
- Criação e seleção de propriedades.
- Modal de arquivamento desktop e mobile e retorno após arquivar.
- Primeira propriedade, ausência de leituras e falha de carregamento.
- Visão geral, login, medidores, alertas e configurações mobile.
- Alternativas escuras de visão geral, login e configurações.
- Paleta, tipografia, estados de controles e guia de navegação.
- Marca baseada na versão 1 aprovada, com gotinha simpática e letras arredondadas.
- Botão de lua no cabeçalho, ao lado do horário de atualização.

### Motion da autenticação no protótipo

As telas de entrar, cadastrar, entrar no mobile e entrar no tema escuro receberam keyframes nativos no Figma.

- Entrada do conteúdo com opacidade de 0 a 1 e deslocamento vertical de 8 px em 300 ms, com pequenos intervalos entre elementos.
- Cena aquática no painel de identidade desktop, com gotinha vetorial flutuante, duas ondas translúcidas em movimentos opostos e círculos de água que expandem e contraem. A timeline tem 12 segundos, com flutuação de 12 px e rotação de até 2 graus. Aplicada ao login, cadastro, tema escuro e estados adicionais de autenticação.
- Troca entre entrar e cadastrar com dissolução de 240 ms.
- Três pranchas adicionais para envio do login, envio do cadastro e erro de autenticação.
- Os botões principais de login e cadastro navegam para o estado de envio. Após 1,1 segundo, o protótipo segue para o próximo passo ilustrativo.
- [Estado de erro](https://www.figma.com/design/Qd38nnUgejHw74QV5gCYAb?node-id=7-626).

A aparência estática do login atualizado, incluindo a composição da gota sobre a água, foi conferida por captura. Os keyframes e as transições foram gravados, mas a reprodução do movimento ainda precisa ser conferida em apresentação. A preferência de movimento reduzido deverá ser respeitada na implementação web.

### Conferência e limites

Foram conferidas capturas da visão geral clara e escura e do modal mobile após a reconstrução. A inspeção estrutural confirmou a quantidade de pranchas e conexões e não encontrou textos ultrapassando horizontalmente seus frames diretos.

As conexões simulam navegação e os números são ilustrativos. A conferência completa de cliques em modo de apresentação segue pendente. Algumas transições mobile levam a detalhes desktop e precisam de refinamento. A reconstrução preserva a direção visual e os fluxos principais, com diferenças de composição em relação ao primeiro arquivo.

Os assets de marca foram produzidos com a ferramenta integrada de geração de imagens, a partir da direção 1 aprovada. A versão clara é transparente. A versão escura é uma prévia sobre fundo escuro e requer acabamento de produção, incluindo correspondência exata entre as variantes e vetorização.

- [Logo clara proposta](docs/design/assets/aquaflow-v2-light.png).
- [Prévia escura proposta](docs/design/assets/aquaflow-v2-dark-preview.png).

O prompt da versão clara pediu uma logo horizontal única com gota aqua simpática e aquaflow em letras minúsculas arredondadas, seguindo a opção 1. O prompt da prévia escura pediu a mesma direção com letras claras em fundo escuro uniforme. Os arquivos representam propostas de marca para o protótipo.

---

## 0. Instrução principal para o Codex

Leia este documento inteiro e, antes de editar, inspecione o repositório e o frontend real. Não assuma que a estrutura descrita aqui continua idêntica: confirme os caminhos, componentes, rotas, estilos, dependências e scripts existentes.

**Não entregue apenas um plano ou mockup. Implemente as melhorias no código**, em etapas pequenas e verificáveis. Preserve o que já funciona. Se alguma sugestão conflitar com a arquitetura atual, adapte-a à arquitetura real e explique a decisão.

Trabalhe no repositório existente. Não crie uma segunda aplicação, não substitua páginas funcionais por telas estáticas e não use dados fictícios para fazer a interface parecer mais bonita.

### Contexto técnico conhecido — confirmar no código antes de agir

- O frontend usa Next.js, React e TypeScript.
- A visualização de gráficos usa Recharts.
- Há CSS próprio e variáveis de tema; não presumir que Tailwind seja o mecanismo principal de estilização.
- Há suporte a tema claro/escuro.
- A marca atual usa a logo `aquaflow-logo.png`.
- O dashboard contém visualizações de consumo, indicadores, acompanhamento, alertas e detalhes técnicos.
- O dashboard já possui bastante lógica no arquivo `frontend/src/app/dashboard/page.tsx` (anteriormente observado com cerca de 2.100 linhas).
- Há componentes de marca/tema em `frontend/src/components/brand.tsx`.
- Os caminhos acima são pistas para a auditoria, não autorização para ignorar a estrutura atual.

---


## Experiência orientada ao cliente

Esta seção complementa o brief original e tem prioridade quando uma recomendação visual anterior expuser detalhes da implementação na experiência principal.

### Objetivo de cada tela

O público principal é uma pessoa que quer acompanhar a água da sua casa. Cada informação deve ajudá-la a entender o consumo, perceber uma mudança, acompanhar um medidor ou decidir uma ação.

- Visão geral deve responder quanto foi consumido, em qual período, como isso se compara ao período anterior e se existe algo a verificar.
- Medidores deve ajudar a identificar cada ponto de medição, consultar a última atualização e entender se está recebendo leituras.
- Alertas deve explicar o que aconteceu, quando, qual medidor está envolvido e quais ações de acompanhamento existem.
- Configurações deve permitir gerenciar as propriedades e ajustar o acompanhamento com linguagem compreensível.

Revisar títulos, rótulos, descrições, mensagens de erro, tooltips, estados vazios, botões e confirmações com essa finalidade. Evitar blocos que apenas repetem contagens ou descrevem a arquitetura.

### Linguagem da interface

Usar frases curtas e explicar unidades e períodos. Termos técnicos devem aparecer apenas quando necessários para executar uma ação ou compreender um resultado. Mensagens de erro devem explicar o efeito para a pessoa e oferecer uma ação de recuperação já disponível.

| Expressão técnica | Direção de linguagem para o cliente |
| --- | --- |
| Inferência, classificação ou predição | Análise do consumo, quando essa informação for necessária |
| Anomalia ou predicted anomaly | Mudança no consumo / consumo fora do padrão, conforme a evidência |
| Telemetria / ingestão | Leituras recebidas / atualização do medidor |
| Worker, pipeline, broker, MQTT, MLflow, versão do modelo | Informações de diagnóstico para documentação e ferramentas técnicas |
| Dados insuficientes | Ainda faltam leituras para analisar este período |
| Dispositivo offline | Medidor sem comunicação, com o horário da última leitura |
| Fluxo mínimo para acompanhar | Vazão mínima para acompanhamento, com L/min e uma explicação curta |
| Janela para leituras atrasadas | Aceitar leituras anteriores, com a duração em dias |

As sugestões devem manter o sentido dos dados e das regras. Não deduzir a causa de uma falha, prometer prazo de recuperação ou apresentar uma mudança como vazamento confirmado.

### Informações que merecem destaque

Priorizar consumo em litros, período, comparação com dados suficientes, última atualização e avisos que a pessoa possa acompanhar. Cada alerta deve apresentar o motivo e suas evidências de forma compreensível.

A lista de **Inferências recentes** foi removida a pedido do usuário e deve continuar fora do dashboard. A análise permanece acessível por meio dos resultados e avisos que já fazem parte da experiência aprovada.

O resumo operacional deve usar linguagem de acompanhamento. Métricas como quantidade de análises ou leituras precisam ter uma finalidade clara antes de ocupar espaço no painel. Não exibir nomes de serviços ou versões de modelo na primeira dobra. Preservar o acesso às funcionalidades existentes de diagnóstico em uma área secundária identificada como **Informações técnicas**, quando esse acesso já existir.

Manter a informação de que análises experimentais sugerem verificação e dependem de dados suficientes. Apresentar essa limitação em linguagem curta, próxima do resultado relevante.

### Fluxos de propriedades já implementados

Preservar e incorporar ao redesign os seguintes comportamentos.

1. A pessoa pode criar a primeira propriedade no início do uso e cadastrar outras em **Configurações → Adicionar propriedade**.
2. Ao criar uma propriedade, o painel seleciona o novo local. O seletor de propriedade deve ter posição consistente, e as informações devem acompanhar a seleção atual.
3. Em **Configurações → Sobre a propriedade**, a ação **Arquivar propriedade** fica no rodapé do cartão, junto das ações de configuração.
4. Ao arquivar, abrir um modal centralizado com o nome da propriedade, a consequência da ação e os botões **Cancelar** e **Confirmar arquivamento**. Usar o modal da aplicação, com contraste, foco e navegação por teclado adequados.
5. Enquanto a solicitação é enviada, mostrar **Arquivando…** e evitar novas submissões. Em caso de falha, manter o contexto e exibir uma mensagem compreensível.
6. Após o arquivamento, a propriedade sai da listagem e do seletor. Selecionar uma propriedade disponível ou mostrar o estado de criação da primeira propriedade quando a lista estiver vazia.
7. O histórico é preservado. A API usa o termo **Arquivar propriedade**. Não apresentar a ação como exclusão definitiva.
8. A propriedade da apresentação, **Casa da Administração**, tem proteção de arquivamento no servidor. A interface deve respeitar essa proteção.
9. O cartão de adicionar propriedade precisa ter espaçamento claro em relação ao cartão de configurações.

A confirmação do arquivamento e o comportamento do seletor fazem parte do produto existente. O redesign deve contemplar sucesso, falha, carregamento, lista vazia e retorno à casa selecionada, inclusive ao atualizar a página.

### Critérios adicionais de conclusão

- [ ] Uma pessoa sem conhecimento de programação entende o consumo e os avisos da primeira tela.
- [ ] Títulos, rótulos e mensagens usam a linguagem do cliente com unidades e períodos claros.
- [ ] O dashboard segue sem a lista de inferências recentes.
- [ ] Diagnóstico técnico tem apresentação secundária e identificação clara.
- [ ] Criar, selecionar e arquivar propriedades funciona com dados da aplicação.
- [ ] Modal de arquivamento funciona com teclado e nos temas claro e escuro.
- [ ] A Casa da Administração mantém a proteção prevista.
- [ ] Informações experimentais e ausência de leituras são comunicadas com precisão.
- [ ] Layout de criação e arquivamento funciona em desktop e mobile.

---

## 1. Direção de arte

### Posicionamento visual

O AquaFlow deve parecer uma **plataforma premium de inteligência e monitoramento hídrico residencial**, e não um painel administrativo genérico.

A interface deve transmitir:

- Confiança e clareza.
- Tecnologia discreta, não futurismo exagerado.
- Inteligência baseada em dados.
- Tranquilidade e controle.
- Precisão e cuidado com detalhes.

Referências de qualidade (não copiar literalmente):

- **Apple:** hierarquia tipográfica, simplicidade, espaçamento e refinamento.
- **Linear:** consistência de componentes, navegação, estados e microinterações.
- **Produtos premium de smart home / IoT:** visualização clara de dispositivos, status e telemetria.
- **CineData, do próprio autor:** usar como referência de ambição visual, identidade e impacto da primeira dobra; não copiar sua estética cinematográfica para o AquaFlow.

### O que evitar

- Não transformar tudo em cards arredondados sem hierarquia.
- Não usar gradientes em todo lugar.
- Não aplicar glassmorphism indiscriminadamente.
- Não usar sombras grandes e difusas como substituto de profundidade.
- Não deixar todos os elementos com a mesma cor de destaque.
- Não exagerar em animações, blur, glow ou efeitos neon.
- Não usar ícones emoji como substitutos de ícones de interface.
- Não diminuir demais os textos auxiliares.
- Não sacrificar contraste ou legibilidade em nome da estética.
- Não fazer uma cópia visual de Apple, Linear ou Netflix.

### Identidade da marca

Adotar a versão 1 da exploração de rebranding aprovada pelo usuário: gota simpática simplificada, olhos pequenos, sorriso discreto e nome aquaflow em letras minúsculas arredondadas. Preservar o aqua e a personalidade acolhedora. Preparar versões com texto escuro para fundo claro e texto claro para fundo escuro, além do símbolo isolado. Conferir legibilidade em tamanhos pequenos antes de substituir o asset no produto.

A cor aqua/turquesa deve permanecer como assinatura, mas não dominar todas as superfícies. Usar cores neutras profundas ou claras como base, com acentos reservados para ações, dados e estados.

### Paleta inicial sugerida

Use os valores como ponto de partida. Primeiro compare com as cores atuais e valide contraste. Ajuste se necessário, mas documente a decisão.

| Token | Dark sugerido | Uso |
|---|---:|---|
| `--bg` | `#0B151A` | Fundo principal |
| `--surface` | `#122229` | Superfícies principais |
| `--surface-raised` | `#192D34` | Elementos elevados / popovers |
| `--surface-subtle` | `#20383E` | Áreas secundárias |
| `--ink` | `#F2F7F7` | Texto principal |
| `--muted` | `#A1B5B9` | Texto secundário |
| `--line` | `#294149` | Bordas e divisores |
| `--aqua` | `#16A6B5` | Cor primária da marca |
| `--aqua-bright` | `#65D5D0` | Destaque pontual em dark |
| `--success` | `#48B98A` | Estado positivo |
| `--warning` | `#E2A56F` | Atenção |
| `--danger` | `#E27676` | Erro / crítico |

Criar também uma paleta light própria, não apenas inverter as cores. Manter contraste AA sempre que possível para texto normal e controles essenciais.

### Tipografia

- Avaliar Geist ou Inter, de preferência com carregamento local/Next Font se compatível com o projeto.
- Definir escala tipográfica consistente: display, h1, h2, h3, body, small, label, caption.
- Usar números tabulares (`font-variant-numeric: tabular-nums`) em métricas, tabelas e leituras.
- Evitar títulos gigantes em todas as telas: reservar escala display para o momento principal do dashboard.
- Garantir legibilidade em resoluções menores.

### Forma, espaçamento e profundidade

Definir tokens globais para:

- Escala de espaçamento (base consistente, por exemplo múltiplos de 4 px).
- Raios de borda (pequeno, médio, grande, painel).
- Bordas e divisores.
- Sombras por nível de elevação.
- Alturas de controles.
- Largura máxima de conteúdo.
- Breakpoints.
- Duração e easing de transições.

Usar superfícies com diferenças sutis de tom e bordas finas. Não depender de sombras para separar todos os elementos.

---

## 2. Design system obrigatório

Antes de redesenhar páginas isoladas, consolidar os fundamentos reutilizáveis.

### Componentes-base

Criar ou evoluir componentes seguindo os padrões já existentes no projeto:

- `Button` — primary, secondary, subtle/ghost, destructive, loading, disabled.
- `IconButton` — com `aria-label`, tooltip quando necessário e foco visível.
- `Card` / `Panel` — variantes default, elevated e interactive apenas quando houver interação.
- `Badge` / `StatusBadge` — success, warning, danger, neutral, info.
- `Input`, `Select`, `Textarea` — label, hint, erro, disabled e focus.
- `Tabs` — estado ativo claro e navegação por teclado.
- `Tooltip` — conteúdo legível, posicionamento robusto e sem cortar em mobile.
- `Dropdown` / `Popover` — fechar com Escape, foco e clique externo conforme padrão da aplicação.
- `Skeleton` — dimensões próximas do conteúdo final para evitar layout shift.
- `EmptyState` — ícone, título, explicação e ação quando fizer sentido.
- `ErrorState` — mensagem compreensível e ação de recuperação.
- `PageHeader` — título, descrição e ações alinhadas.
- `SectionHeader` — título, contexto e ação opcional.

Não criar abstrações desnecessárias. Reutilizar componentes existentes se já cumprirem bem a função. Evitar duplicar estilos e componentes com nomes diferentes para a mesma coisa.

### Regras de qualidade

- Estados hover, active, focus-visible, disabled, loading e error devem ser definidos.
- Toda interação deve funcionar por teclado.
- Botões precisam ter estados de foco visíveis.
- Inputs devem ter labels reais, não depender apenas de placeholders.
- Ícones devem seguir uma única biblioteca já instalada ou uma solução consistente existente.
- Não adicionar bibliotecas grandes sem necessidade.
- Não introduzir `any` para contornar tipagem.
- Não usar `!important` como estratégia de arquitetura de CSS.
- Não duplicar tokens entre arquivos.

---

## 3. Estrutura global e navegação

Avaliar a navegação atual e redesenhar a estrutura para que todas as áreas pareçam partes do mesmo produto.

### Direção recomendada

Considerar uma sidebar elegante e responsiva:

- Logo no topo.
- Navegação principal: Visão geral, Medidores, Alertas.
- Área secundária: Configurações.
- Propriedade selecionada / seletor de propriedade em local consistente.
- Indicador discreto de quantidade de alertas não resolvidos.
- Controle de tema no canto superior direito do conteúdo, ao lado do horário de atualização.
- Botão compacto com ícone de lua em traço fino, cantos arredondados, borda discreta e fundo coerente com o tema. Usar aproximadamente 40–44 px para área de interação e ícone de 18–20 px.
- Oferecer nome acessível que indique a ação, como “Ativar tema escuro” ou “Ativar tema claro”, tooltip e foco visível. O tema atual determina a ação do botão.
- No mobile, manter o botão no cabeçalho sem sobrepor a marca ou os dados de atualização.
- Acesso ao perfil/sair em posição previsível.
- Sidebar colapsável no desktop, se isso fizer sentido com as rotas.
- Drawer acessível no mobile.

Não mudar nomes, rotas, permissões ou comportamento de navegação sem necessidade. A navegação visual deve continuar apontando para as páginas reais.

### Header e conteúdo

- Definir um container principal com largura máxima consistente.
- Dar espaço suficiente entre header, título da página e conteúdo.
- Manter alinhamento comum entre páginas.
- Evitar que cada rota implemente seu próprio header com espaçamentos diferentes.
- Em mobile, reorganizar ações e filtros sem overflow horizontal.

---


---

## 4A. Autenticação — login premium e primeira impressão

**A tela de login faz parte obrigatória deste redesign.** Não considerar o trabalho concluído se apenas as páginas internas forem atualizadas.

Antes de implementar, localizar todas as rotas e componentes reais de autenticação: login, cadastro (se existir), recuperação/redefinição de senha, verificação de e-mail ou outras etapas que já façam parte do produto. Não inventar fluxos que não existem; melhorar visualmente e em usabilidade os fluxos encontrados.

### Direção visual da tela de login

Criar uma experiência de entrada com qualidade de produto premium, coerente com a identidade AquaFlow e com o restante do sistema.

Direção recomendada:

- Layout limpo, editorial e sofisticado.
- Logo AquaFlow em posição de destaque, sem exagero.
- Fundo com profundidade visual sutil: gradiente atmosférico, formas fluidas ou ondas abstratas inspiradas em água.
- Um painel de autenticação com excelente contraste, hierarquia e espaçamento.
- Campos, labels, botão principal, links e mensagens de erro com o mesmo design system das telas internas.
- Texto de boas-vindas curto, humano e coerente com o produto.
- Em telas largas, considerar composição em duas áreas: uma área de identidade/manifesto visual e outra de formulário. Em telas pequenas, priorizar o formulário e simplificar o fundo.
- A composição deve continuar elegante com animações desativadas e em telas de baixo desempenho.

Evitar uma tela genérica de template SaaS. Não usar uma fotografia de banco de imagens como elemento principal. Não deixar o formulário pequeno ou perdido em uma tela vazia.

### Conteúdo e hierarquia

A tela deve deixar claro:

1. Marca AquaFlow.
2. Mensagem de boas-vindas / acesso à conta.
3. Campo de e-mail ou identificador conforme autenticação atual.
4. Campo de senha.
5. Controle mostrar/ocultar senha, se compatível.
6. Opção de lembrar sessão, somente se já existir e for segura.
7. Link de recuperação de senha, se o fluxo existir.
8. Botão principal com estados normal, loading, sucesso e erro.
9. Mensagens de validação claras e próximas do campo.
10. Links secundários (cadastro, termos ou suporte) apenas se já forem parte do produto.

### Comportamento e segurança — preservar rigorosamente

- Não alterar o provedor de autenticação, endpoints, payloads, cookies, tokens, sessão, middleware, redirects ou regras de autorização.
- Não armazenar senha ou token em `localStorage`/`sessionStorage` por conveniência visual.
- Não expor detalhes internos de autenticação em mensagens de erro.
- Não remover proteções contra submissão repetida.
- Não quebrar o fluxo de redirect para a página de destino após login.
- Não alterar a política de sessão ou logout.
- Não criar login social, cadastro ou recuperação de senha fictícios.
- O botão de mostrar senha deve apenas alternar a visibilidade do campo, sem alterar o valor.
- Inputs devem funcionar com autofill e gerenciadores de senha (`autocomplete`, `name`, `type` apropriados).
- O formulário deve funcionar por teclado e em leitores de tela.
- Erros devem ser anunciados de forma acessível e não depender apenas de cor.

### Estados obrigatórios

Desenhar e implementar:

- Estado inicial.
- Foco nos campos.
- Campo preenchido.
- Senha visível/oculta, se aplicável.
- Validação de campo.
- Credenciais inválidas.
- Erro de rede/servidor.
- Envio em andamento.
- Sucesso e redirecionamento.
- Recuperação de senha, caso exista.
- Layout mobile.

Não simular login bem-sucedido. Ligar os componentes à autenticação já existente.

### Animação específica da tela de login

Adicionar movimento sutil e elegante, com preferência por CSS e recursos já disponíveis:

- Fundo com gradiente muito lento ou formas fluidas deslocando-se poucos pixels.
- Elemento abstrato de água/gota com flutuação leve, se combinar com a logo e não competir com o formulário.
- Entrada inicial do logo, título e formulário com fade + pequeno deslocamento vertical.
- Foco dos campos com transição suave de borda e halo discreto.
- Botão com transição de cor, elevação mínima e feedback de pressionamento.
- Mensagens de erro e sucesso com transição curta, sem sacudir a tela.
- Respeitar `prefers-reduced-motion`; nesse modo, remover movimento decorativo e manter apenas mudanças essenciais de estado.
- Evitar animação infinita chamativa, parallax agressivo, partículas excessivas, cursor customizado e efeitos que prejudiquem digitação ou leitura.

---

## 8A. Política de motion — dar vida sem exagerar

O AquaFlow deve ter uma linguagem de movimento consistente. O movimento precisa comunicar hierarquia, resposta e continuidade; não servir como decoração constante.

### Intensidade desejada

**Nível: sutil a moderado.** A pessoa deve perceber que a interface é bem acabada, mas conseguir ignorar as animações enquanto usa o produto.

### Onde animar

| Elemento | Movimento recomendado | Intensidade |
|---|---|---|
| Entrada de página | Fade + deslocamento vertical de 6–12 px | Sutil |
| Cards principais | Entrada escalonada curta, sem atraso longo | Sutil |
| Botões | Cor, borda e deslocamento de 1 px no press | Sutil |
| Campos | Transição de borda/halo no foco | Sutil |
| Sidebar | Transição de largura e opacidade ao expandir | Moderada |
| Dropdown/popover | Fade + escala muito pequena | Sutil |
| Gráficos | Desenho/entrada inicial moderada; tooltip responsivo | Moderada |
| Indicadores numéricos | Contagem animada apenas na primeira entrada, se não causar confusão | Sutil |
| Elemento aquático decorativo | Flutuação lenta e amplitude pequena | Sutil |
| Feedback de ação | Mudança de estado clara e rápida | Sutil |

### Regras de implementação

- Preferir `transform` e `opacity` para animações, evitando animar propriedades que provoquem layout/reflow.
- Usar durações curtas e consistentes: aproximadamente 140–220 ms para feedback de controles e 220–420 ms para transições de conteúdo.
- Animações decorativas lentas podem durar mais, mas devem ter baixa amplitude e não competir com conteúdo.
- Evitar atrasos em cascata longos; o usuário não deve esperar para interagir.
- Não animar continuamente números, alertas, status ou dados em tempo real.
- Não animar gráficos novamente a cada atualização se isso atrapalhar a leitura.
- Não usar movimento para esconder carregamentos lentos ou mascarar falta de feedback.
- Respeitar `prefers-reduced-motion` em todos os componentes.
- Garantir que conteúdo e controles estejam disponíveis mesmo se animações não forem executadas.
- Se o projeto já possuir biblioteca de motion, avaliar seu uso antes de adicionar outra dependência. Se não possuir, preferir CSS para interações simples.
- Evitar dependências pesadas para resolver transições pequenas.

### Sensação desejada

O resultado deve lembrar um produto premium bem polido: interface responsiva, fluida e agradável, com pequenos detalhes que recompensam a interação. Não deve parecer um site de apresentação cheio de efeitos nem um painel futurista de ficção científica.


## 4. Dashboard — a tela de maior impacto

A primeira dobra deve comunicar rapidamente o estado da propriedade e o valor do AquaFlow.

### Hierarquia recomendada

1. Contexto da propriedade e saudação/título.
2. Um bloco principal de consumo, com valor, unidade e período.
3. Comparação com período anterior, sem esconder se é aumento ou redução.
4. Estado geral do monitoramento, com linguagem precisa.
5. Gráfico principal de consumo.
6. Resumo do acompanhamento e alertas.
7. Detalhes técnicos em uma área secundária/expansível.

### Hero de consumo

Criar um destaque visual que seja claramente o elemento principal, sem transformar todo o dashboard em um banner gigante.

Deve apresentar:

- Valor total do período.
- Unidade.
- Intervalo temporal.
- Comparação com período equivalente anterior.
- Tendência, se houver dados suficientes.
- Contexto sobre períodos sem leitura, quando relevante.

O valor deve vir dos dados reais já fornecidos pela aplicação. Não inventar valores, metas ou classificações.

### Métricas secundárias

Reorganizar medidores, leituras e alertas para que:

- Cada métrica tenha rótulo curto e inequívoco.
- A unidade esteja clara.
- O período de referência esteja visível.
- Estados de ausência de dados não sejam mostrados como zero.
- Não haja redundância entre cards.

### Gráfico de consumo

Aprimorar o gráfico existente (Recharts ou tecnologia atual), mantendo a origem dos dados e o comportamento funcional.

Implementar, quando compatível com os dados:

- Tooltip customizado, alinhado ao design system.
- Eixos discretos e legíveis.
- Gridlines sutis.
- Destaque do ponto ativo.
- Área/linha com tratamento visual refinado.
- Seletor de período com estado ativo evidente.
- Legenda e unidade claras.
- Responsividade real.
- Estado de carregamento e estado sem dados.
- Tratamento de períodos sem leitura: ausência de amostra não pode ser representada como consumo zero.

Não suavizar curvas de forma que distorça a leitura dos dados. Não inventar pontos intermediários.

### Resumo do acompanhamento

A área de acompanhamento deve explicar o que os dados disponíveis mostram, não apenas repetir números.

Separar visualmente:

- Leituras recebidas.
- Análises realizadas.
- Sinais de mudança.
- Avisos criados.
- Distribuição horária.
- Motivos dos avisos.

Explicar que sinal de mudança não confirma, sozinho, um problema. Preservar textos de cautela já existentes e melhorar sua apresentação.

### Detalhes técnicos

Aplicar a seção de experiência orientada ao cliente. Preservar informações de diagnóstico já existentes em uma área secundária acessível, com nomes compreensíveis para o público. Detalhes de infraestrutura e modelos devem ficar na documentação ou no contexto técnico apropriado.

---

## 5. Medidores

Transformar a tela de medidores em uma central de dispositivos.

Cada item deve permitir identificar rapidamente:

- Nome / identificador do medidor.
- Propriedade ou local associado, se disponível.
- Estado de comunicação.
- Última leitura e horário.
- Vazão ou volume, conforme dado disponível.
- Indicador de dado desatualizado, quando aplicável.
- Acesso a detalhes e histórico, se a funcionalidade já existir.

### Estados visuais

- Conectado: positivo, mas discreto.
- Sem comunicação: atenção clara, sem alarmismo.
- Leitura atrasada: informar há quanto tempo.
- Sem dados: explicar que não há leitura suficiente.
- Carregando / erro: usar skeleton e estado de recuperação.

Não inferir que um medidor está funcionando corretamente apenas porque existe um registro antigo. Respeitar o status retornado pelo backend.

---

## 6. Alertas

A tela de alertas deve funcionar como uma central de ocorrências, com leitura rápida e detalhes acessíveis.

### Organização

- Separar alertas ativos, reconhecidos/resolvidos conforme os estados reais existentes.
- Exibir tipo, severidade, dispositivo relacionado, período e status.
- Ordenar segundo a lógica atual do produto; não alterar regras de priorização sem aprovação.
- Filtros e busca devem funcionar com os dados reais.
- Contagem dos alertas deve corresponder aos registros exibidos.

### Cartão/detalhe do alerta

- Título objetivo.
- Descrição curta e compreensível.
- Severidade e estado.
- Data/hora.
- Medidor relacionado, se houver.
- Evidências técnicas em seção expansível.
- Ações existentes (reconhecer, resolver etc.) com confirmação e feedback.

### Linguagem responsável

Um sinal/anomalia não deve ser apresentado como vazamento confirmado se a regra ou o modelo apenas detectou uma mudança. Não converter probabilidade experimental em certeza. Preservar a distinção entre alerta, indício, análise e confirmação.

---

## 7. Configurações

Organizar as configurações por grupos visuais e manter a semântica dos campos:

- Dados da propriedade.
- Fuso horário.
- Unidade de volume.
- Limites e duração de fluxo contínuo.
- Janela para leituras atrasadas.
- Outras opções já existentes.

Melhorias:

- Labels persistentes.
- Descrição contextual curta.
- Unidades junto aos campos.
- Validação inline.
- Feedback de salvamento.
- Estado dirty (alterações não salvas), se possível.
- Ações salvar/descartar bem diferenciadas.
- Não perder valores preenchidos em caso de erro.
- Não alterar defaults ou regras de validação sem justificativa.

---

## 8. Motion e microinterações

Movimento deve dar feedback e continuidade, nunca atrapalhar.

Aplicar com parcimônia:

- Transições curtas de cor, borda e superfície.
- Entrada discreta de seções e cards.
- Animação de gráfico apenas quando não prejudicar leitura.
- Feedback de botão ao salvar ou executar ação.
- Skeleton shimmer sutil, se já houver padrão compatível.
- Indicador de conexão com animação discreta apenas quando representar estado real.

Respeitar `prefers-reduced-motion`. Não animar números continuamente nem fazer a interface parecer um painel de ficção científica.

---

## 9. Responsividade e acessibilidade

Testar no mínimo:

- Desktop largo: 1440 px.
- Laptop: 1280 px.
- Tablet: 768 px.
- Mobile: 390 px.
- Mobile estreito: 360 px.

Critérios:

- Sem scroll horizontal global.
- Gráficos redimensionam corretamente.
- Sidebar vira navegação mobile utilizável.
- Cards mudam de colunas de forma coerente.
- Ações não ficam escondidas.
- Tabelas/listas têm alternativa responsiva quando necessário.
- Alvos de toque confortáveis.
- Contraste adequado.
- Foco visível.
- Labels e landmarks semânticos.
- Estados não comunicados somente por cor.
- `prefers-reduced-motion` respeitado.

---

## 10. Restrições críticas: preservar produto e dados

Este redesign é principalmente visual. Portanto:

1. **Não alterar contratos de API**: endpoints, métodos HTTP, payloads, schemas, autenticação, tratamento de sessão ou nomes de campos.
2. **Não alterar backend**, banco, migrations, workers, MQTT, pipelines ou modelos de ML por conveniência estética.
3. **Não substituir dados reais por mocks** em páginas funcionais.
4. Não remover funcionalidades existentes para simplificar o layout.
5. Não trocar rotas sem manter compatibilidade.
6. Não mudar regras de cálculo, janelas de tempo, timezone ou unidades.
7. Não converter ausência de leitura em zero.
8. Não declarar vazamento confirmado com base apenas em sinal/anomalia.
9. Não remover avisos de caráter experimental ou limitações dos dados.
10. Não armazenar segredos, tokens ou dados pessoais no frontend.
11. Não introduzir dependências sem necessidade clara.
12. Se uma mudança visual exigir mudança de contrato ou regra de negócio, **pare e proponha a alteração separadamente**, sem implementá-la silenciosamente.

---

## 11. Plano de implementação

Executar em fases. Ao final de cada fase, rodar verificações e corrigir regressões antes de avançar.

### Fase 0 — Auditoria e baseline

- Inspecionar estrutura, rotas, componentes, estilos e dependências.
- Identificar sistema atual de temas e tokens.
- Identificar todos os componentes compartilhados.
- Mapear estados de loading, empty, error e success.
- Registrar scripts disponíveis para lint, typecheck, testes e build.
- Rodar baseline de lint/typecheck/testes/build que existirem.
- Identificar screenshots ou ferramentas de browser disponíveis; se houver, registrar baseline visual das páginas.
- Não alterar comportamento nesta fase.

**Entregável:** resumo curto do estado atual, riscos e plano de arquivos a alterar.

### Fase 1 — Fundamentos visuais

- Consolidar tokens de cor, tipografia, spacing, radius, shadow e motion.
- Refinar tema claro e escuro separadamente.
- Atualizar fontes de maneira compatível com Next.js.
- Padronizar controles e componentes-base.
- Verificar contraste e foco.

**Critério de conclusão:** as páginas existentes continuam funcionais e já compartilham a mesma linguagem visual.

### Fase 2 — Shell e navegação

- Redesenhar sidebar/header/container.
- Implementar comportamento desktop/mobile.
- Preservar rotas e ações existentes.
- Padronizar PageHeader e SectionHeader.

**Critério de conclusão:** navegar por todas as áreas não parece trocar de produto.

### Fase 3 — Autenticação e dashboard

- Redesenhar login e demais telas de autenticação existentes.
- Validar estados de autenticação, autofill, acessibilidade e responsividade.
- Preservar integralmente os fluxos e contratos de autenticação.
- Em seguida, redesenhar a hierarquia e primeira dobra do dashboard.

- Redesenhar hierarquia e primeira dobra.
- Evoluir hero de consumo e métricas.
- Refinar gráficos e tooltips.
- Melhorar acompanhamento e detalhes técnicos.
- Implementar estados de loading/empty/error.

**Critério de conclusão:** dashboard visualmente forte, legível e fiel aos dados.

### Fase 4 — Medidores, alertas e configurações

- Aplicar design system às demais páginas.
- Melhorar organização e hierarquia.
- Preservar ações, filtros, validações e fluxos existentes.
- Conferir estados reais de cada recurso.

**Critério de conclusão:** consistência visual entre todas as rotas, sem perda funcional.

### Fase 5 — Polimento

- Microinterações.
- Responsividade fina.
- Acessibilidade.
- Ajustes de densidade e espaçamento.
- Remoção de CSS morto/duplicado que tenha sido substituído com segurança.

**Critério de conclusão:** sem regressões conhecidas e experiência refinada em desktop e mobile.

---

## 12. Verificações obrigatórias

Antes de encerrar, verificar também os critérios adicionais de experiência do cliente e os fluxos de propriedades descritos no início deste documento.

Antes de encerrar:

- Rodar lint.
- Rodar typecheck, se existir.
- Rodar testes existentes.
- Rodar build de produção.
- Corrigir erros introduzidos pelo redesign.
- Conferir todas as rotas.
- Testar tema claro e escuro.
- Testar loading, vazio, erro e dados preenchidos.
- Testar formulários e ações de alertas.
- Testar login real, logout, redirects, erros de credenciais, loading e recuperação de senha quando existente.
- Conferir autofill e gerenciadores de senha na tela de login.
- Testar responsividade nos tamanhos definidos.
- Confirmar que nenhum endpoint, payload, cálculo ou regra de negócio foi alterado.

Se não houver testes visuais automatizados, usar browser/screenshot tooling disponível no ambiente. Não afirmar que uma tela foi visualmente validada se ela não foi aberta/renderizada.

### Relatório final do Codex

Ao terminar, informar:

1. O que mudou por página.
2. Quais componentes e tokens foram criados/reutilizados.
3. Arquivos principais alterados.
4. Comandos de validação executados e resultados.
5. Testes visuais/responsivos realmente realizados.
6. Qualquer limitação ou dívida técnica restante.
7. Confirmação explícita de que contratos de API e regras de negócio foram preservados — ou listar precisamente qualquer exceção aprovada.

---

## 13. Prompt para iniciar no Codex

Depois de colocar este arquivo na raiz do repositório, envie:

```text
Leia integralmente CODEX_AQUAFLOW_REDESIGN.md e execute o redesign descrito nele, incluindo a experiência orientada ao cliente e os fluxos de propriedades.

Comece pela Fase 0: audite o frontend real, confirme a arquitetura e rode os checks disponíveis para registrar o baseline. Em seguida, implemente as fases em ordem, sem parar apenas em recomendações ou mockups.

Prioridades:
1. Qualidade visual premium e consistência entre todas as rotas.
2. Tela de login premium e todos os estados/fluxos de autenticação já existentes.
3. Dashboard com primeira dobra marcante e excelente hierarquia.
4. Design system reutilizável e motion sutil a moderado.
5. Responsividade e acessibilidade.
6. Preservação total de dados, integrações, autenticação, API e regras de negócio.

Faça mudanças incrementais, valide cada fase e corrija regressões. Não use dados mockados em telas funcionais. Não altere backend ou contratos de API para resolver questões visuais.

Se o escopo for grande para uma única execução, conclua uma fase funcional e validada por vez, atualize este documento com o progresso e continue a partir da próxima fase. Não deixe uma reformulação parcialmente quebrada.
```

---

## 14. Prompt para revisão visual crítica

Depois da implementação, enviar este segundo prompt:

```text
Faça uma revisão crítica do frontend AquaFlow como um diretor de design de produto e engenheiro frontend sênior.

Abra/renderize todas as rotas disponíveis, incluindo login e demais telas de autenticação, em desktop e mobile. Não se limite a ler o CSS.

Procure especificamente:
- inconsistência de espaçamento, alinhamento, tipografia e densidade;
- cards sem hierarquia ou com excesso de bordas;
- cores de destaque usadas em excesso;
- textos pequenos ou com contraste insuficiente;
- gráficos com eixos/tooltips/legendas pouco refinados;
- estados vazios, loading e erro mal resolvidos;
- sidebar/header desalinhados entre rotas;
- overflow, quebras e ações inacessíveis em mobile;
- componentes duplicados ou estilos conflitantes;
- animações excessivas ou sem propósito.

Faça as correções diretamente no código. Preserve a API, os dados e as regras de negócio. Rode novamente lint, typecheck, testes e build. Ao final, apresente os problemas encontrados, as correções realizadas e o que não conseguiu validar.
```

---

## Resultado esperado

O resultado não deve ser apenas um dashboard escuro e bonito. Deve ser um produto coerente, com:

- Identidade própria.
- Hierarquia visual clara.
- Design system consistente.
- Navegação refinada.
- Tela de login premium, com autenticação real preservada.
- Motion sutil a moderado que dê vida sem distrair.
- Dados fáceis de interpretar.
- Gráficos com acabamento profissional.
- Estados de interface bem resolvidos.
- Responsividade real.
- Acessibilidade.
- Funcionalidade preservada.

**A métrica de sucesso é simples:** qualquer pessoa deve conseguir navegar pelo AquaFlow e sentir que está usando um produto real, maduro e cuidadosamente projetado — sem que a interface prometa mais do que os dados e o sistema realmente entregam.

## Andamento da implementação

Branch de trabalho: `feat/frontend-redesign`, criada sobre `feat/ml-dataset-hibrido`. Nenhuma mudança foi commitada.

- **Fase 0 — Auditoria e baseline:** concluída. Frontend Next.js 16/React 19 com CSS global próprio, tema claro/escuro e Recharts. Não foi adicionada dependência.
- **Fase 1 — Fundação visual:** primeira versão dos tokens claro/escuro, tipografia de sistema, controles e movimento reduzido aplicada; marca aprovada usada na autenticação e no shell.
- **Fase 2 — Shell e navegação:** primeira versão implementada com navegação lateral no desktop e barra inferior no mobile; o botão de tema fica ao lado da atualização na visão geral e permanece acessível nas outras telas.
- **Autenticação:** tela de acesso com cena aquática animada, entrada curta do formulário, alternância entre entrar/cadastrar e controle acessível para mostrar/ocultar a senha. A responsividade foi ajustada no CSS, mas ainda precisa de inspeção visual em navegador.
- **Preservação funcional:** fluxo de login/cadastro, endpoints e payloads existentes foram mantidos. Propriedades, medidores, alertas e dashboard não tiveram regras ou contratos alterados.
- **Verificações desta fatia:** lint, formatação, typecheck, 2 testes existentes, `git diff --check` e build passaram. O Next.js 16.4.0 exibiu um aviso de vulnerabilidade conhecido; a compilação prosseguiu após repetir o comando. A atualização de dependência foi deixada fora do escopo atual do redesign.
- **Inspeção visual:** pendente. Não foi feita validação em navegador nesta fatia.

Próxima etapa: revisar visualmente a navegação desktop/mobile e aplicar a nova hierarquia à visão geral, preservando todos os dados e gráficos reais; depois avançar por medidores, alertas e configurações.
