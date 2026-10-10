# Avaliação de dados para desenvolvimento de ML

## Recomendação

Manter o conjunto **Unitywater – Digital water meter data, July 2022** como referência externa para exploração e para aproximar o formato da telemetria do AquaFlow. Ele contém leituras de medidores digitais e campos relacionados a fluxo, temperatura, bateria, sinal de rádio e pressão; o catálogo descreve medições em residências e alguns estabelecimentos comerciais da Sunshine Coast. O recurso é publicado sob licença CC BY 4.0 ([catálogo e recurso oficial](https://www.data.qld.gov.au/dataset/ea562792-0de2-422a-9c0e-5175bafcea5c/resource/9fcbd9cf-ee34-4e85-a44f-8afdebdb5237)).

Esse alinhamento torna o conjunto útil para EDA, conferir unidades e cadência, testar preparação de séries temporais e orientar o schema de ingestão. A cópia local não foi comparada por hash com o arquivo do catálogo, então sua equivalência exata ainda precisa ser confirmada antes de atribuir a ela os metadados e a licença da fonte.

## Limitação para treinamento e avaliação

O catálogo consultado descreve medições e atributos dos medidores, mas não documenta rótulos ou confirmação de vazamentos. Assim, não devemos apresentar esse conjunto como base rotulada para treinar e medir um classificador de vazamentos. Ele pode apoiar métodos exploratórios ou não supervisionados, desde que isso seja explicitado e que os resultados sejam interpretados com cautela.

Para avançar antes de existir telemetria do ESP32, gerar dados mockados reproduzíveis com cenários normais, anômalos e incompletos, com rótulos que indiquem os cenários criados. Essa avaliação verifica o pipeline e a capacidade de reconhecer os cenários simulados; não comprova generalização para vazamentos ou consumo reais.

## Alternativas e uso complementar

- O conjunto **Smart Meter Water Consumption Measurements** registra consumo cumulativo de 17 residências por aproximadamente um ano, com resolução temporal fina. É útil para estudar séries domésticas, lacunas e reamostragem, mas não fornece rótulos de vazamento na descrição consultada; confirme a licença antes de redistribuir ou incorporar os arquivos ([registro Zenodo](https://zenodo.org/records/7506076), [artigo dos autores](https://www.mdpi.com/2224-2708/12/3/46)).
- O conjunto da **NTNU/SINTEF** contém medições de rede e eventos de vazamento identificados, o que pode servir como exercício complementar de detecção com eventos. A escala é uma rede de distribuição, não uma residência, e os eventos não devem ser tratados como representativos dos medidores domésticos do AquaFlow. Confirme a licença antes de redistribuir ([registro Zenodo](https://zenodo.org/records/14001028)).

Nenhuma dessas alternativas substitui diretamente o conjunto de julho: a primeira é mais próxima de séries domésticas, enquanto a segunda possui eventos de vazamento registrados, porém em outra escala operacional. A descrição do catálogo Unitywater também lista recursos de maio e junho de 2022, que podem ser avaliados se mais cobertura temporal for necessária ([página do conjunto Unitywater](https://www.data.qld.gov.au/dataset/digital-water-meter-dataset-explanation)).

## Decisão prática

1. Começar o pipeline e a comparação de modelos com dados mockados, versionados e reproduzíveis no próprio projeto.
2. Usar Unitywater como referência para comparar schema, unidades, qualidade e características de telemetria; não misturar essas observações com rótulos simulados sem identificar a origem.
3. Se a entrega precisar de exemplos externos com eventos identificados, avaliar NTNU/SINTEF em um experimento separado e declarar a diferença de escala.
4. Reavaliar a validade dos modelos quando houver telemetria real coletada pelo ESP32.

## Fontes consultadas

- Queensland Government, [Unitywater – Digital Water Meter data](https://www.data.qld.gov.au/dataset/digital-water-meter-dataset-explanation) e [recurso de julho de 2022](https://www.data.qld.gov.au/dataset/ea562792-0de2-422a-9c0e-5175bafcea5c/resource/9fcbd9cf-ee34-4e85-a44f-8afdebdb5237).
- Zenodo, [Smart Meter Water Consumption Measurements](https://zenodo.org/records/7506076); autores, [artigo de descrição do conjunto](https://www.mdpi.com/2224-2708/12/3/46).
- Zenodo, [NTNU/SINTEF sewer network and smart water meter data with leak events](https://zenodo.org/records/14001028).
