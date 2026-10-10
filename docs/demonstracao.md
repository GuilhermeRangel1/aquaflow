# Demonstração do AquaFlow

Este roteiro demonstra, sem ESP32, a entrada MQTT, a persistência no PostgreSQL, o treinamento com dados simulados, o registro no MLflow, a inferência e os indicadores do dashboard.

## Iniciar

Na raiz do projeto, rode:

```powershell
docker compose up --build -d
docker compose ps
```

Entre em [http://localhost:3000](http://localhost:3000) com `demo@example.com` e `AquaFlow-demo-123!`. A propriedade **Casa da demonstração** tem leituras e alertas de exemplo. Na visão geral, o quadro **Saúde da ingestão e do modelo** apresenta a quantidade de leituras e os estados do MQTT, da inferência e das regras. Ele atualiza a cada 30 segundos.

Na primeira inicialização sem artefato de modelo, o serviço `ml-trainer` gera uma série sintética reproduzível, faz a análise e preparação, compara classificadores e registra a execução no MLflow. Depois, `ml-inference` processa as leituras válidas ainda não avaliadas. Essa preparação pode levar alguns minutos. Acompanhe os serviços com:

```powershell
docker compose logs -f ml-trainer ml-inference api mqtt-ingestor
```

O painel pode mostrar o worker como **Indisponível** enquanto o treinamento ainda não terminou. Se o artefato já existir, o Compose o reutiliza e ignora o treinamento. O MLflow fica em [http://localhost:5000](http://localhost:5000).

## Enviar uma leitura MQTT

Na tela **Medidores**, cadastre um medidor com série exclusiva e copie a chave exibida. No PowerShell, publique uma leitura com essa série e chave:

```powershell
docker compose run --rm -e DEVICE_SERIAL=AF-MQTT-001 -e DEVICE_KEY=COLE_A_CHAVE -e CUMULATIVE_VOLUME_LITERS=1000 mqtt-publisher
```

Publique outra leitura depois, usando o mesmo medidor e volume acumulado maior, por exemplo `1000.5`. Confira a última leitura em **Medidores** e a mudança nos indicadores de ingestão. A API aceita a leitura, preserva o evento e o worker avalia a leitura válida quando houver histórico suficiente. Um resultado de ML é experimental e separado dos alertas das regras.

Para executar a verificação automatizada do trajeto MQTT → API → PostgreSQL com recursos isolados de teste:

```powershell
docker compose -p aquaflow-mqtt-test -f docker-compose.yml -f docker-compose.test.yml --profile test run --build --rm mqtt-e2e
docker compose -p aquaflow-mqtt-test -f docker-compose.yml -f docker-compose.test.yml --profile test down --volumes
```

## Repetir treinamento

Para gerar e treinar novamente com a seed definida no Compose, rode:

```powershell
docker compose run --build --rm -e ML_RETRAIN_MODEL=true ml-trainer
docker compose restart ml-inference
```

O Airflow fica em [http://localhost:8080](http://localhost:8080). O DAG `aquaflow_mock_telemetry_pipeline` pode ser habilitado e executado pela interface para repetir a geração, análise e preparação. O treinamento automático do Compose usa os mesmos scripts diretamente.

## Decisões e limites

- MQTT é um transporte de entrada; o ingestor encaminha as mensagens à API HTTP, que valida o dispositivo e persiste a telemetria.
- O dashboard mostra contagens de leituras e alertas limitadas à propriedade autenticada. Os contadores do MQTT são agregados para o broker compartilhado; os estados dos workers descrevem os serviços do Compose. Nenhum desses indicadores expõe mensagens, credenciais ou dados de outra propriedade.
- O serviço de inferência registra previsões experimentais. Os detectores por regras continuam rodando independentemente do modelo; uma falha de ML não interrompe o monitoramento existente.
- Os dados e rótulos usados para treinar são simulados. A avaliação mede os cenários artificiais criados pelo gerador e não comprova desempenho em residências reais nem identifica fisicamente vazamentos.
- A integração com hardware ainda exige escolher e calibrar placa e sensor, além de validar conectividade, unidades e qualidade de sinal com leituras reais.
- A leitura MQTT de teste exige um medidor cadastrado e sua chave individual. Credenciais padrão do Compose são somente para desenvolvimento local.

Para encerrar sem apagar o banco local, use `docker compose down`. Os dados do gerador, modelos e execuções permanecem em `data/ml/`.
