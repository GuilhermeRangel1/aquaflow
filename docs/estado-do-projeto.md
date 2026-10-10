# Estado atual do projeto

**AquaFlow é um protótipo acadêmico integrado.** O estado abaixo descreve o que o repositório e o Compose oferecem hoje; não é uma declaração de prontidão para operação em residências ou em produção.

## Resumo por área

| Área | Estado no protótipo | O que isso significa |
| --- | --- | --- |
| Interface e conta demonstrativa | Implementadas | O Compose inicia a aplicação, a conta local e uma propriedade com dados sintéticos para explorar telas e fluxos. |
| API e PostgreSQL | Implementados para desenvolvimento | Há autenticação, ownership por propriedade, cadastro de medidores, ingestão, persistência, consumo, alertas e indicadores operacionais. |
| Ingestão HTTP | Implementada | Leituras podem ser recebidas pela API, inclusive por simuladores; credenciais de medidor e repetição de evento são verificadas. |
| Ingestão MQTT | Integrada localmente | O broker e o consumidor encaminham mensagens para a mesma API. O contrato foi exercitado sem depender de um ESP32 físico. |
| Monitoramento por regras | Implementado | Detectores determinísticos criam alertas com explicação e evidências. Eles seguem operando sem depender de ML. |
| Pipeline e modelos de ML | Implementados como experimento | O pipeline compara classificadores e registra resultados, mas treina com cenários e rótulos simulados. |
| Inferência na aplicação | Experimental | O worker persiste previsões associadas à versão do modelo. Previsões positivas podem criar alertas experimentais separados dos alertas por regras. |
| Airflow e MLflow | Disponíveis localmente | Airflow permite executar manualmente geração, análise e preparação; MLflow apresenta os experimentos do treinamento. Ambos usam configuração local de demonstração. |
| Firmware e hardware | Ainda não implementados | Há guias e contratos, mas não há código FreeRTOS para compilar, placa/sensor selecionados ou calibração física. |
| Uso real e produção | Ainda não validados | Faltam coleta de telemetria física, validação do modelo com dados reais, hardening operacional e infraestrutura de produção. |

## Dados mockados: onde são usados

Há dois usos diferentes de dados simulados:

1. **Demonstração da aplicação:** o seed do backend prepara uma conta, uma propriedade, três medidores ativos, histórico de consumo, exemplos de alertas e algumas leituras para demonstrar a inferência. O seed é idempotente e preserva o histórico; não é um fluxo de coleta de um sensor.
2. **Experimentos de ML:** `ml/generate_mock_data.py` cria uma série temporal separada, com seed fixa, cenários e rótulos artificiais. Ela é usada na análise, na preparação, na comparação e na avaliação dos modelos.

Os arquivos gerados e os modelos ficam em `data/`, que não é versionada. Os valores exibidos no demo, os alertas de exemplo e o desempenho dos modelos não devem ser apresentados como medições ou confirmações de vazamento em campo.

## O que os resultados de ML permitem concluir

Os experimentos mostram que a infraestrutura de preparação, validação temporal, busca de hiperparâmetros, comparação e inferência funciona sobre os cenários programados. Na execução de referência, o Random Forest atingiu AP 1,000 no teste temporal padrão, mas AP 0,438 no perfil `shifted` e 0,569 no perfil `stress`. Esse contraste evidencia sensibilidade a mudanças de rotina simuladas. Consulte [Resultado do experimento](../ml/docs/resultado-experimento.md) para métricas completas, hashes e ambiente reproduzível; os parâmetros usados estão em [Métricas e parâmetros](metricas-e-parametros.md).

Eles **não** demonstram que o modelo detecta vazamentos reais, que generaliza para diferentes casas ou medidores, ou que deixou de sofrer overfitting. Os testes com perfis deslocado e de estresse são verificações artificiais de sensibilidade, não substitutos de uma coleta independente de telemetria real e de rótulos confiáveis.

Quando houver dados de hardware, não basta trocar um arquivo CSV ou substituir o artefato do modelo. Será preciso definir como coletar e validar leituras, criar rótulos justificáveis, preparar uma amostra temporal independente e rever as métricas e os critérios antes de usar previsões em decisões de produto.

## O que falta para uma validação física

- Escolher a placa ESP32 e o sensor de vazão.
- Implementar as tarefas FreeRTOS de leitura, calibração, relógio, fila de reenvio e publicação.
- Validar unidade, frequência, precisão, reconexão e perda de mensagens no hardware.
- Definir e proteger o acesso remoto do dispositivo; a configuração MQTT padrão atual é interna ao Compose e não oferece TLS para uma placa fora dessa rede.
- Coletar telemetria em condições reais e planejar rótulos ou avaliação sem rótulos adequada.
- Refazer a avaliação do modelo com separação temporal e conjunto independente representativo do uso pretendido.

## Uso e segurança

O projeto é preparado para desenvolvimento e apresentação em uma máquina local. A conta demo, senhas padrão, acesso local do Airflow sem autenticação e demais configurações do Compose não são credenciais ou controles de produção. O arquivo `.env.example` contém valores de demonstração; troque os segredos antes de qualquer ambiente compartilhado e não publique a instância local.

Para instalar e demonstrar a solução, siga [Demonstração e execução local](demonstracao.md). A organização dos serviços e os fluxos de dados estão em [Arquitetura](arquitetura.md); detalhes dos experimentos ficam em [Dados e modelos](../ml/README.md).
