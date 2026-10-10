# Dados externos considerados para ML

## Decisão usada no protótipo

O pipeline ativo do AquaFlow usa **dados mockados gerados pelo próprio projeto**. O conjunto Unitywater – Digital water meter data, July 2022 foi pesquisado como possível referência externa, mas não é consumido pelo Compose, pelo treinamento ou pelo notebook. Nenhum modelo atual foi treinado com esse dataset.

A decisão de começar com dados simulados permite testar geração, validação, preparação, divisão temporal, comparação de modelos e inferência antes de haver hardware. Os rótulos representam apenas cenários construídos pelo gerador. Consulte [dados mockados](dados-mockados.md) para conhecer sua distribuição e limitações.

## Unitywater como referência de schema

O conjunto **Unitywater – Digital water meter data, July 2022** contém leituras de medidores digitais e campos relacionados a fluxo, temperatura, bateria, sinal de rádio e pressão; o catálogo descreve medições em residências e alguns estabelecimentos comerciais da Sunshine Coast. O recurso é publicado sob licença CC BY 4.0 ([catálogo e recurso oficial](https://www.data.qld.gov.au/dataset/ea562792-0de2-422a-9c0e-5175bafcea5c/resource/9fcbd9cf-ee34-4e85-a44f-8afdebdb5237)).

Ele pode servir para uma futura exploração de formato, unidades e cadência. A cópia local não foi comparada por hash com o recurso do catálogo; portanto, sua equivalência exata e os metadados/licença aplicáveis à cópia não foram confirmados. Não inclua a cópia no treino atual nem a apresente como rotulada para vazamentos.

## Limite para treino e avaliação

A descrição do catálogo não documenta rótulos ou confirmação de vazamentos. O dataset pode apoiar EDA ou estudos não supervisionados, desde que a origem e a escala sejam identificadas, mas não pode ser tratado como verdade-terreno para avaliar um classificador supervisionado de vazamentos.

Outras fontes também têm limitações: **Smart Meter Water Consumption Measurements** descreve séries domésticas cumulativas sem rótulos de vazamento documentados ([registro Zenodo](https://zenodo.org/records/7506076), [artigo dos autores](https://www.mdpi.com/2224-2708/12/3/46)); o conjunto **NTNU/SINTEF** contém eventos identificados em rede de distribuição, escala diferente da instalação residencial do AquaFlow ([registro Zenodo](https://zenodo.org/records/14001028)). Confirme licença e compatibilidade antes de redistribuir ou usar esses arquivos.

## Próxima transição para dados reais

A telemetria recebida por HTTP/MQTT é persistida na aplicação, mas o trainer atual lê tabelas preparadas geradas pelo fluxo sintético; ele não extrai automaticamente leituras do PostgreSQL. Incorporar telemetria física exigirá uma etapa explícita de extração e qualidade, política de privacidade, decisão sobre rótulos, divisão temporal independente e avaliação adequada à finalidade. Não basta substituir o CSV ou trocar o arquivo do modelo.

## Fontes

- Queensland Government, [Unitywater – Digital Water Meter data](https://www.data.qld.gov.au/dataset/digital-water-meter-dataset-explanation) e [recurso de julho de 2022](https://www.data.qld.gov.au/dataset/ea562792-0de2-422a-9c0e-5175bafcea5c/resource/9fcbd9cf-ee34-4e85-a44f-8afdebdb5237).
- Zenodo, [Smart Meter Water Consumption Measurements](https://zenodo.org/records/7506076); autores, [artigo de descrição do conjunto](https://www.mdpi.com/2224-2708/12/3/46).
- Zenodo, [NTNU/SINTEF water network and meter data](https://zenodo.org/records/14001028).
