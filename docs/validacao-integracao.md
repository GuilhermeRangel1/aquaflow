# Validação da integração antes das telas técnicas

Execução de 20/11/2026 sobre o commit `0fae51e`, na branch
`feat/frontend-redesign`. O ambiente principal usa o projeto Compose
`aquaflow-hybrid-check`. Os testes de publicação usam também
`aquaflow-preflight-test`, com PostgreSQL, API, broker e consumidor próprios.
O publicador usado nesta rodada é um simulador MQTT.

## Airflow e MLflow

`docker compose -p aquaflow-hybrid-check up -d --build` concluiu.
API, banco, frontend, Airflow, MLflow, consumidor MQTT, broker e worker ficaram
saudáveis. Os serviços de inicialização terminaram com código zero.

O contêiner antigo do Airflow tinha código 255 e `OOMKilled=false`.
A falha não se repetiu após reconstruir e iniciar o ambiente. A causa da saída
anterior permanece indeterminada.

O DAG `aquaflow_hybrid_telemetry_pipeline` foi habilitado e executado pelo CLI
do serviço. A execução `preflight_20261120_113406` terminou com sucesso.

| Tarefa | Resultado |
| --- | --- |
| generate_data | success |
| analyze_data | success |
| prepare_data | success |
| train_candidate | success |

A consulta de erros de importação de DAGs retornou uma lista vazia.
O treino ficou no experimento `aquaflow-hybrid-airflow`, ID `2`.
Os quatro candidatos concluíram e cada classificador treinável registrou
quatro tentativas de busca, totalizando 12 tentativas.

| Candidato | ID da execução no MLflow | AP na validação temporal |
| --- | --- | --- |
| Baseline de prevalência | c038a8fe6b89485bbc894f52033386ee | 0,149 |
| KNN | 0cbc7ca5a2b34905951e97bf0144765c | 0,144 |
| Árvore de Decisão | 1880d3a082574e42937cf5cb1f32c6eb | 0,988 |
| Random Forest | 91ccebd66da44286ae8cd826ba9d4938 | 0,998 |

Essas métricas descrevem a validação temporal. A seleção também considera a
rotina alterada, e o perfil de estresse é avaliado depois. O Random Forest foi
selecionado. Seu hash coincide com o relatório e com a versão usada pelo worker:
`7e9b90465de703130d7f2d3fbc4a3eb62675bb1a58f414fc29ed3cffc08ef9e0`.

O cliente do MLflow recuperou o relatório, o manifesto das partições, as
matrizes de confusão de validação e teste e o modelo serializado. Os demais
candidatos possuem parâmetros, métricas, matrizes de validação e, quando
aplicável, execuções filhas de busca.

Os arquivos dessa execução ficam em
`data/ml/airflow/eaf6f055be6316b2c86f9e374ab7ef7b523c93793ebf1433344010aeabca6b89/training/`.
São artefatos locais, ignorados pelo Git. A interface do experimento pode ser
aberta em [MLflow local](http://localhost:5000/#/experiments/2).

## Notebook e visualizações

As 13 células de código de
`ml/notebooks/01_exploracao_e_avaliacao.ipynb` foram executadas em sequência
no ambiente Python de treino do Airflow, com backend gráfico Agg.
A preparação passou, com 4.511 observações e cobertura de 97,9%.
A seção de teste avaliou 1.128 amostras, com AP de 0,999.

Foram geradas oito imagens em `data/ml/notebook/figures/`, incluindo comparação
dos candidatos, matrizes, precisão/recall e curvas ROC. A imagem de comparação
foi inspecionada visualmente. O notebook versionado mantém as células sem saídas.
O notebook usa o modelo de inicialização, cujo hash coincide com o candidato
produzido nesta rodada.

## MQTT, PostgreSQL e inferência

Os três testes de integração existentes passaram em 62,77 segundos no ambiente
isolado. Eles verificaram publicação e reenvio sem duplicação, inferência com
cadências de 300 e 30 segundos, dados insuficientes, previsão normal, previsão
positiva, agrupamento do aviso, reconhecimento e resolução.

```powershell
docker compose -p aquaflow-preflight-test -f docker-compose.yml -f docker-compose.test.yml --profile test --profile ml-test run --build --rm -e AQUAFLOW_MQTT_E2E=1 mqtt-ml-e2e python -m pytest -q tests/test_mqtt_compose_flow.py
```

Também foram executados 12 testes de consulta e autorização de inferências,
exportação e seed usando PostgreSQL com schemas temporários. Todos passaram.

```powershell
docker compose -p aquaflow-hybrid-check -f docker-compose.yml -f docker-compose.test.yml --profile test run --rm tests python -m pytest -q tests/test_ml_inference_api.py tests/test_export_training_data.py tests/test_demo_dataset.py
```

Na aplicação principal foi criada uma conta de teste independente, com a
propriedade `Validação MQTT e ML` e o medidor
`e52c8be7-427e-4f8c-80f2-ccd436bcf993`. A propriedade tem ID
`468de0e2-affc-4782-a13f-39dd6d40e433`. Os dados ficam preservados nessa conta
como evidência sintética. As credenciais foram geradas em memória.

| Verificação na aplicação principal | Resultado |
| --- | --- |
| Publicação MQTT com QoS 1 | Seis eventos enviados |
| Reenvio da última publicação | Seis eventos únicos persistidos |
| Consulta direta no PostgreSQL | Seis leituras e seis inferências |
| Previsões normais | Duas |
| Previsões positivas | Duas |
| Dados insuficientes | Duas inferências skipped |
| Consulta de estado do medidor | Última leitura corresponde ao evento recém-enviado |
| Consulta de consumo | Intervalos válidos disponíveis |
| Aviso experimental | Criado |
| Inferências sem autenticação | HTTP 401 |
| Inferências de propriedade inexistente ou inacessível | HTTP 404 |

O evento recém-enviado tem ID `00cc7aa528e0494d9833bae8535d40d4`.
A API expõe seus horários de medição e recepção. Os cenários de classificação
usaram timestamps passados controlados e aceitos pela janela de ingestão.

## O que fica pronto para as próximas telas

- A telemetria pode usar as consultas existentes de leituras e estado do medidor.
- A tela de inferências pode consultar os resultados, a versão, as features e
  as explicações disponíveis na API.
- A tela de experimentos pode ser construída sobre os dados validados no
  MLflow. O acesso administrativo e a API que apresentará esses dados ao
  frontend ainda precisam ser implementados.

A validação física com ESP32, sensor e Wi-Fi continua pendente. O relatório
SBC, as telas técnicas e o ensaio completo da apresentação seguem como entregas
futuras.

## Auditoria das métricas e da generalização

Oito conjuntos de métricas foram recalculados a partir dos datasets e
previsões: validação temporal e rotina alterada dos três candidatos, teste do
modelo final e estresse. AP, precisão, recall, F1, acurácia, acurácia balanceada
e matrizes coincidiram com os relatórios. Os hashes também coincidiram.

As partições principais têm 2.255 observações de treino, 1.128 de validação e
1.128 de teste, com índices distintos e ordem temporal preservada. Os três
folds foram reproduzidos com os parâmetros vencedores. A normalização do KNN é
ajustada dentro do pipeline em cada fold. As features não contêm rótulos.

| Modelo | AP média no treino dos folds | AP média na validação dos folds | Interpretação |
| --- | --- | --- | --- |
| KNN | 1,000 | 0,159 | Forte diferença compatível com overfitting |
| Árvore de Decisão | 0,914 | 0,903 | Pequena diferença nos folds temporais |
| Random Forest | 1,000 | 0,964 | Diferença de 0,036 nos folds temporais |

O KNN também tem recall zero na validação principal com limiar 0,5. Sua AP
fica próxima da referência de prevalência de 0,149. Esse resultado desfavorável
deve constar da comparação dos candidatos.

O Random Forest final tem AP de 0,997 e recall de 99,0% no conjunto usado no
ajuste final. No teste padrão, tem AP de 0,999 e recall de 99,4%. Esses resultados
não indicam underfitting global do modelo selecionado nesse perfil.

No estresse reservado, a AP cai para 0,502 e o recall para 5,56% no limiar 0,5:
40 verdadeiros positivos, 679 falsos negativos, 157 falsos positivos e 3.635
verdadeiros negativos. A acurácia de 81,5% deve ser interpretada junto da baixa
sensibilidade e da prevalência positiva de 15,9%.

O mesmo artefato congelado foi avaliado em nove séries novas: standard, shifted
e stress, com seeds 318, 571 e 904 e datas em dezembro. Essas séries não foram
usadas para ajustar o modelo ou escolher parâmetros.

| Perfil novo | AP nas três séries | Recall no limiar 0,5 |
| --- | --- | --- |
| standard | Aproximadamente 1,00 | Aproximadamente 99% a 100% |
| shifted | Aproximadamente 0,98 | Aproximadamente 91% a 92% |
| stress | 0,501 a 0,517 | 1,95% a 3,06% |

As séries adicionais usam o mesmo gerador e calibração. Elas reforçam a
sensibilidade ao perfil, sem estabelecer generalização em campo. O baixo recall
no estresse exige investigação do limiar, das features e dos cenários de treino,
com validação independente para qualquer alteração posterior.

### Limite da avaliação temporal final

O treino final inclui treino e validação de setembro e o perfil shifted de
outubro. O teste principal está em setembro. O código não usa seus rótulos
para ajustar o modelo, mas esse teste não é estritamente posterior a todos os
dados do ajuste final. Ele deve ser descrito como um holdout do perfil padrão
após ajuste combinado.

Um ensaio adicional, mantendo os parâmetros escolhidos e ajustando o Random
Forest apenas em treino e validação anteriores ao teste de setembro, produziu
AP de 0,9992 e recall de 99,4%. Esse ensaio mantém a seleção anterior de
parâmetros e o mesmo gerador.

As métricas estão numericamente consistentes. Há evidência de overfitting no
KNN e falha relevante de generalização do Random Forest sob estresse. Os dados
disponíveis não sustentam afirmar ausência de overfitting ou underfitting em
todos os cenários.

A saída detalhada está em `data/ml/preflight-20261120/ml-audit.json`,
arquivo local ignorado pelo Git. Para interpretar as diferenças entre treino
e validação, consulte as
[curvas de aprendizado do scikit-learn](https://scikit-learn.org/stable/modules/learning_curve.html)
e as [orientações sobre vazamento de informação](https://scikit-learn.org/stable/common_pitfalls.html).

## Correção do sobreajuste — branch híbrida

As alterações seguintes estão locais em `feat/ml-dataset-hibrido`.
O teste de regressão reproduziu a diferença de AP de 0,841 do KNN antes
da correção. A nova busca usa medições em vez do calendário, votos uniformes
com vizinhanças maiores e árvores de profundidade dois ou três. A escolha
prefere a configuração mais simples dentro de um erro padrão do melhor
resultado, com uma separação de 12 amostras entre treino e validação.

O perfil deslocado é gerado antes da série principal. A CLI rejeita dados
de ajuste que alcancem o início do teste. Para a série padrão, o ajuste termina
em 12/09/2026 às 23h55 e o teste começa em 13/09/2026 às 00h, no fuso local.

O DAG `regularized_final_20261120_115532` concluiu as quatro etapas.
O novo artefato selecionado é o KNN de 201 vizinhos, com hash
`c683a28abd80e9e396b32d9f7f7094c65fcdc778c1608baccd5a72b4bcfb06d0`.
O worker local foi reiniciado com esse artefato. O anterior foi preservado
em `data/ml/preflight-20261120/previous-active-model/`.

| Classificador | Diferença AP treino/CV | AP no ajuste final | AP no teste padrão | Recall no estresse |
| --- | --- | --- | --- | --- |
| KNN | 0,018 | 0,982 | 0,994 | 91,8% |
| Random Forest | 0,015 | 0,942 | 0,947 | 91,4% |
| Árvore de Decisão | 0,021 | 0,941 | 0,947 | 91,4% |

O KNN selecionado tem precisão de 93,7% e recall de 97,6% no teste padrão.
No estresse, tem precisão de 92,7% e recall de 91,8%. Os três candidatos agora
têm seus artefatos e métricas finais de treino, teste e estresse registrados
no MLflow depois da seleção.

| Classificador | ID da nova execução no MLflow |
| --- | --- |
| Baseline | e9a1a6eba9b14115bb4b3bbe2c71b60c |
| KNN | 997ed9d8282a44a290b9c9761fedd5a8 |
| Random Forest | f2cc0a0115b64bc2bc152507565744a1 |
| Árvore de Decisão | a3c25ce632644332aacedfe5ede65483 |

Os três modelos congelados foram avaliados em nove séries reservadas,
com seeds 1201, 2503 e 3701 e datas em dezembro. O recall no estresse ficou
entre 90,8% e 94,2%, com precisão entre 91,2% e 96,3%. Os resultados completos
estão em `data/ml/preflight-20261120/regularization-audit.json`.
O notebook também executou com o novo artefato.

As diferenças entre treino e validação diminuíram, e os resultados reservados
melhoraram. O KNN ainda tem desvio de AP de 0,132 entre folds, sinalizado como
instabilidade em um diagnóstico separado do sobreajuste. As primeiras divisões
contêm menos dados, e a nova regularização reduz sua capacidade de ajuste.
Essa variação precisa continuar visível na apresentação.

Os perfis usados na auditoria anterior já influenciaram o desenvolvimento.
As novas seeds avaliam o mesmo gerador e calibração. Nenhum desses resultados
garante ausência de sobreajuste ou desempenho de campo.

### Correção da instabilidade do KNN

Uma investigação posterior reproduziu o desvio de AP de 0,132. O KNN fixo usava
201 vizinhos tanto no fold de 554 amostras quanto no ajuste de 7.894 amostras.
Nos folds, a AP de validação era 0,655, 0,819 e 0,980, acompanhando a quantidade
de dados e o excesso de suavização nas primeiras divisões.

O estimador agora escolhe uma proporção entre 1% e 2,5% das amostras de cada
ajuste. A proporção selecionada foi 2,5%: 14, 28 e 42 vizinhos nos folds e
198 vizinhos no ajuste final. A regra faz parte do estimador serializado em
`ml/estimators.py` e é distribuída na imagem de treinamento e inferência.

O teste de regressão falhou com o desvio anterior e passou após a mudança.
As nove verificações de ML passaram. O DAG `stable_knn_20261120_120547`
concluiu, e o notebook executou com o novo modelo.

| Indicador do KNN | Resultado após correção |
| --- | --- |
| AP média no treino dos folds | 0,987 |
| AP média na validação dos folds | 0,967 |
| Diferença treino/validação | 0,020 |
| Desvio da AP entre folds | 0,0165 |
| AP média de seleção | 0,937 |
| AP no teste padrão | 0,994 |
| Recall no teste padrão | 97,6% |
| Precisão no estresse | 92,7% |
| Recall no estresse | 91,8% |

O artefato ativo tem hash
`8f77c382fbc3ac0bd3c5404091c48d694d83d0f4063f6307bbb409f679520d02`.
O anterior, de vizinhança fixa, está preservado em
`data/ml/preflight-20261120/previous-fixed-neighborhood/`.

Os três candidatos foram avaliados, congelados, em nove séries adicionais
com seeds 4817, 5923 e 6101. No estresse, o recall ficou entre 91,1% e 92,2%,
com precisão entre 90,5% e 95,6%. A saída detalhada está em
`data/ml/preflight-20261120/stable-knn-audit.json`.

O diagnóstico do KNN deixou de sinalizar diferença elevada entre treino e
validação ou instabilidade nos folds desta execução. A limitação de avaliação
com dados do mesmo gerador continua válida.
