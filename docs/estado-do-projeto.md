# Estado atual do AquaFlow

O AquaFlow é um protótipo acadêmico de monitoramento de água. Para subir o ambiente, siga o [guia de demonstração](demonstracao.md). Para conferir evidências e critérios de entrega, consulte a [issue #3](https://github.com/GuilhermeRangel1/aquaflow/issues/3).

| Área | O que a aplicação entrega |
| --- | --- |
| Aquisição | API HTTP e ingestão MQTT com validação, idempotência e persistência no PostgreSQL. O firmware ESP32 está implementado com publicação padrão a cada cinco segundos. |
| Demonstração | O Compose carrega uma série calibrada na conta demo e treina o modelo se o artefato inicial estiver ausente. Os quatro CSVs e a calibração estão no Git. A rotina e os rótulos são simulados. |
| Medidores e telemetria | Conexão, vazão e leituras recentes atualizadas automaticamente. A Área Técnica mostra a associação entre leitura, inferência e versão do modelo. |
| Visão geral | Consumo e detalhes expansíveis. Nos detalhes, a visão semanal agrupa os dados por dia e a mensal por semana. A rosca distingue os volumes dentro do padrão, que vale verificar e sem conclusão. A estimativa usa a tarifa residencial de referência de Recife. |
| Alertas | Regras determinísticas funcionam em paralelo com previsões experimentais. Cada aviso identifica o medidor e pode ser reconhecido, resolvido ou marcado como falso positivo. |
| Treinamento | Comparação temporal de modelos e rastreamento no MLflow. O DAG manual do Airflow gera um candidato separado. Na aplicação, o administrador pode solicitar retreinamento da série calibrada e promoção após validação. |

Para telemetria de alta frequência, a inferência exige uma janela válida de cinco minutos. O painel consegue exibir as leituras antes disso. Um volume sinalizado representa água que passou durante um intervalo para verificar, sem comprovar vazamento ou quantificar desperdício.

## Validação e próximos passos

- O trajeto MQTT → API → PostgreSQL → inferência foi exercitado com simulador. Falta repetir com ESP32 e sensor físicos, verificando calibração, reconexão e chegada das leituras durante a apresentação.
- O desempenho de ML foi medido em séries simuladas calibradas em bancada. Para inferir desempenho em residências, o modelo precisa de avaliação física independente. Veja a [execução de referência](validacao-integracao.md).
- O Compose é destinado à demonstração local. Antes de qualquer uso em produção, revise segredos, autenticação dos serviços, isolamento de rede e TLS.
