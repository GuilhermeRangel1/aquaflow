# Dados e modelos

Esta pasta concentra o trabalho de machine learning do AquaFlow. Por enquanto, contém um gerador reproduzível de telemetria simulada e a avaliação das fontes de dados. Ainda não há pipeline de treinamento, modelo validado ou inferência em produção.

## Gerar dados simulados

Na raiz do repositório:

```powershell
docker compose run --build --rm ml-data-generator
```

O arquivo é criado em `data/mock-ml/readings.csv`, fora do controle de versão. Para mudar seed, período ou intervalo, passe o comando completo ao serviço:

```powershell
docker compose run --build --rm ml-data-generator python generate_mock_data.py --seed 7 --days 16 --interval-minutes 5
```

O gerador usa apenas a biblioteca padrão do Python e também pode ser executado com `python ml/generate_mock_data.py` na raiz do projeto. Veja [schema, cenários e limitações](docs/dados-mockados.md) e [avaliação das fontes externas](docs/avaliacao-dataset.md).

O futuro pipeline de preparação, experimentos e modelos deve ficar nesta pasta. A interface de integração com a aplicação é a telemetria persistida e, quando houver um modelo validado, um resultado versionado com evidências. Os detectores por regras da API permanecem disponíveis.
