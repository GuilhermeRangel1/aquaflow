# Glossário do AquaFlow

- **Protótipo:** versão integrada para demonstração e avaliação acadêmica. Não implica validação em hardware real nem prontidão de produção.
- **Dado mockado/sintético:** registro gerado por código para reproduzir cenários controlados. Não foi medido em uma residência nem deve ser apresentado como evidência de vazamento real.
- **Leitura válida:** amostra de telemetria que passou pelas validações do pipeline.
- **Observação preparada:** leitura válida com uma leitura válida anterior, permitindo calcular o delta do volume acumulado e a duração do intervalo.
- **Feature:** variável usada como entrada do modelo. No experimento atual, deriva de vazão, volume, intervalo e horário local; identificadores e rótulos ficam de fora.
- **Rótulo simulado:** classe atribuída pelo gerador para indicar qual cenário ele construiu. Não é um diagnóstico de campo.
- **Partição temporal:** divisão cronológica entre treino, validação e teste, para avaliar em períodos posteriores aos usados no ajuste.
- **Perfil deslocado/de estresse:** séries sintéticas com rotinas, ruídos ou intensidades diferentes das da série principal. Servem para investigar sensibilidade dentro do simulador.
- **Anomalia simulada:** rótulo produzido pelo gerador para identificar um cenário construído. Não confirma vazamento nem representa um rótulo obtido em campo.
- **Inferência:** previsão de um modelo sobre uma leitura válida, acompanhada da probabilidade estimada e da versão do modelo.
- **Alerta do modelo:** alerta experimental criado quando uma inferência positiva indica comportamento que merece verificação; é independente dos alertas gerados por regras.
- **Alerta por regras:** alerta produzido por condições determinísticas e explicáveis sobre leituras e janelas observadas. Continua ativo mesmo quando o worker de ML está indisponível.
- **Airflow:** ferramenta que, nesta demonstração, orquestra manualmente geração, análise e preparação de dados. O DAG atual não inicia o treinamento.
- **MLflow:** interface e armazenamento local de parâmetros, métricas e artefatos dos experimentos de treinamento.
