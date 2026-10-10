# Glossário do AquaFlow

- **Leitura válida:** amostra de telemetria que passou pelas validações do pipeline.
- **Observação preparada:** leitura válida com uma leitura válida anterior, permitindo calcular o delta do volume acumulado e a duração do intervalo.
- **Anomalia simulada:** rótulo produzido pelo gerador para identificar um cenário construído. Não confirma vazamento nem representa um rótulo obtido em campo.
- **Inferência:** previsão de um modelo sobre uma leitura válida, acompanhada da probabilidade estimada e da versão do modelo.
- **Alerta do modelo:** alerta experimental criado quando uma inferência positiva indica comportamento que merece verificação; é independente dos alertas gerados por regras.
