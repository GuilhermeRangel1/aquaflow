# Resultado de referência do experimento de ML

Este relatório registra uma execução do pipeline atual para que os resultados possam ser discutidos e comparados. **Todos os dados e rótulos são simulados pelo AquaFlow.** As métricas indicam somente como os modelos reconheceram os padrões construídos pelo gerador; não estimam detecção de vazamentos em residências.

## Identificação da execução

| Campo | Valor |
| --- | --- |
| Data da execução | 10/10/2026 |
| Revisão do código | `645f182e45cfc753da828aca92c17535e4dff11f` |
| Python | 3.12.6 |
| scikit-learn | 1.8.0 |
| MLflow | 3.16.0 |
| Tarefa | Classificação binária de `anomaly_label`, por leitura válida após uma leitura anterior |
| Dados-base | 16 dias, intervalos de 5 min, início em 01/09/2026, fuso `America/Sao_Paulo`, seed 42 |
| Preparação | 4.512 leituras presentes; 96 lacunas; 4.511 observações preparadas após excluir lacunas e primeira leitura sem predecessor |
| Divisão cronológica | Treino: 2.255; validação: 1.128; teste: 1.128 |
| Limiar de classificação | 0,5 |
| Busca | 4 amostras de hiperparâmetros por modelo, 3 folds temporais, seed 42 |
| SHA-256 dos arquivos de treino preparados | `49abfaaf2c3d2eaa7988727638e76115b67cedf7d08053d085a30321a69a7056` |
| SHA-256 do modelo selecionado | `e13e1696eae70d6d0ace770b3c18f39d8759c70bf6e0959c7a5b0ee53b8c02de` |

A série principal contém 4.608 intervalos esperados. O gerador marcou 3.840 como normais, 288 como fluxo contínuo, 384 como consumo noturno e 96 como leitura ausente. O `anomaly_label` classifica como positiva qualquer cenário diferente de `normal`; não representa diagnóstico de campo.

## Comparação usada na seleção

A seleção usa a média da average precision (AP) da validação cronológica principal e de uma validação com perfil `shifted`. O perfil `stress` fica fora da seleção e é avaliado somente depois. A validação cruzada temporal, com três folds, roda no bloco de treino.

| Candidato | AP na validação principal | AP no perfil `shifted` | Média usada na seleção |
| --- | ---: | ---: | ---: |
| Baseline de prevalência | 0,149 | 0,181 | 0,165 |
| Regressão logística | 0,274 | 0,400 | 0,337 |
| HistGradientBoosting | 0,965 | 0,289 | 0,627 |
| Random Forest | 0,946 | 0,438 | 0,692 |

O modelo selecionado foi **Random Forest**, com `max_depth=6`, `max_features=sqrt`, `min_samples_leaf=20` e `n_estimators=100`. A busca temporal apresentou AP média de 0,978 nos folds de validação e 1,000 nos folds de treino; diferença de 0,022 e desvio de 0,031 entre folds de validação.

## Avaliação final

O teste cronológico contém dados posteriores aos blocos usados para treino e seleção, mas vem do mesmo gerador e perfil `standard`.

| Conjunto | AP | Precisão | Recall | F1 | Matriz de confusão (TN, FP / FN, TP) |
| --- | ---: | ---: | ---: | ---: | --- |
| Teste temporal `standard` | 1,000 | 0,994 | 1,000 | 0,997 | `[[959, 1], [0, 168]]` |
| Validação `shifted` | 0,438 | 0,608 | 0,269 | 0,373 | `[[3555, 141], [596, 219]]` |
| Teste `stress` | 0,569 | 0,482 | 0,797 | 0,601 | `[[3176, 616], [146, 573]]` |

O resultado muito alto no teste temporal não deve ser lido isoladamente. No perfil `shifted`, a AP cai para 0,438; no perfil `stress`, fica em 0,569. O diagnóstico heurístico não encontrou grande diferença entre treino e validação cruzada temporal (`0,022`), mas sinalizou sensibilidade à mudança de distribuição: a diferença de AP entre validação principal e `shifted` foi `0,508`, e a AP de estresse ficou abaixo do sinal de investigação `0,7`.

**Conclusão limitada:** o Random Forest reconhece muito bem os padrões do perfil temporal padrão, mas sua resposta se degrada quando a rotina simulada muda. A execução não prova generalização para outras casas, sensores ou tipos de anomalia, e não permite declarar o modelo livre de overfitting. Os perfis auxiliares também são artificiais; a validação adequada depende de telemetria independente e rótulos justificáveis.

## Como reproduzir

Instale as dependências indicadas em [`ml/requirements-training.txt`](../requirements-training.txt). Na raiz do repositório, gere, analise, prepare e treine a série:

```powershell
python ml/generate_mock_data.py --output data/ml/experimento/raw/mock_readings.csv --seed 42 --start 2026-09-01T00:00:00-03:00 --timezone America/Sao_Paulo --days 16 --interval-minutes 5
python ml/prepare_dataset.py analyze --input data/ml/experimento/raw/mock_readings.csv --output-dir data/ml/experimento/analysis --timezone America/Sao_Paulo
python ml/prepare_dataset.py prepare --input data/ml/experimento/raw/mock_readings.csv --output-dir data/ml/experimento/prepared --timezone America/Sao_Paulo
python ml/train_model.py --features data/ml/experimento/prepared/features.csv --labels data/ml/experimento/prepared/labels.csv --metadata data/ml/experimento/prepared/metadata.csv --output-dir data/ml/experimento/training --timezone America/Sao_Paulo --seed 42 --search-iterations 4 --tracking-uri sqlite:///data/ml/experimento/mlflow.db
```

O trainer gera automaticamente os perfis `shifted` e `stress`. Os arquivos serão criados em `data/ml/experimento/`, caminho ignorado pelo Git; os resultados resumidos neste documento são a referência versionada para a revisão de código indicada acima.

Para uma nova execução, preserve os artefatos anteriores ou use outra pasta e registre a revisão do código, versões das dependências, hashes, parâmetros, métricas por partição e limitações. Não substitua silenciosamente os resultados deste relatório: eles identificam uma execução específica, não um desempenho permanente do produto.

## Fontes dos parâmetros

- [Parâmetros e métricas do projeto](../../docs/metricas-e-parametros.md)
- [Geração dos dados simulados](../generate_mock_data.py)
- [Preparação das features e rótulos](../prepare_dataset.py)
- [Treinamento, seleção e avaliação](../train_model.py)
- [Limites do conjunto externo pesquisado](avaliacao-dataset.md)
