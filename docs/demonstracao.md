# Demonstração e execução local

Este guia explica como iniciar o protótipo, observar o que cada processo está fazendo e demonstrar os caminhos principais sem hardware físico. A demonstração usa uma conta local e dados sintéticos; não representa medição real de uma residência.

## 1. Pré-requisitos

- Docker Desktop instalado, aberto e com Docker Compose v2 disponível.
- Memória suficiente para PostgreSQL, frontend, API, treinamento e Airflow. A primeira inicialização pode levar mais tempo porque imagens e artefatos de ML ainda precisam ser preparados.
- Portas locais `3000`, `5000`, `5432`, `8000` e `8080` disponíveis. O broker MQTT fica apenas na rede interna do Compose.

Na raiz do repositório, opcionalmente copie `.env.example` para `.env` caso queira alterar senha do banco, JWT, conta demonstrativa ou credenciais MQTT. Os padrões são somente para desenvolvimento local.

## 2. Subir a aplicação

Execute um único comando:

```powershell
docker compose up --build
```

O Compose constrói e inicia os serviços integrados. Na ordem lógica:

1. PostgreSQL fica pronto.
2. API aplica as migrations e prepara a conta, a propriedade, medidores e amostras sintéticas da demonstração.
3. Broker MQTT e consumidor ficam disponíveis; o consumidor encaminha mensagens para a API HTTP.
4. MLflow fica disponível para registrar experimentos.
5. Se não houver artefato treinado, `ml-trainer` gera outra série sintética, analisa, prepara e compara os modelos. Ele termina normalmente ao concluir.
6. `ml-inference` inicia depois do treinamento e avalia as leituras compatíveis já persistidas e as que chegarem depois.
7. Frontend e Airflow ficam acessíveis localmente. O DAG Airflow não é acionado automaticamente; ele deve ser habilitado e executado pela interface.

Acesse:

- Aplicação: [http://localhost:3000](http://localhost:3000)
- OpenAPI da API: [http://localhost:8000/docs](http://localhost:8000/docs)
- Prontidão da API: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- MLflow: [http://localhost:5000](http://localhost:5000)
- Airflow: [http://localhost:8080](http://localhost:8080)

A conta de demonstração padrão é:

```text
E-mail: demo@example.com
Senha: AquaFlow-demo-123!
Propriedade: Casa da demonstração
```

## 3. O que aparece na conta demo

O seed do backend cria três medidores ativos: **Medidor principal**, **Irrigação externa** e **Demonstração ML**. Ele acrescenta histórico sintético de consumo, atividade programada de irrigação, uma sequência curta para mostrar a inferência e exemplos de alertas em estados diferentes. O seed é aditivo e preserva histórico existente; reiniciar o serviço não limpa o banco.

Os registros exibidos nessa propriedade são dados de demonstração, não mensagens transmitidas por um medidor físico. Os alertas históricos são amostras de interface e os novos alertas por regra dependem das leituras e janelas observadas. As previsões do modelo são experimentais e aparecem separadas dos detectores por regras.

## 4. Acompanhar inicialização e treinamento

Para ver o estado dos serviços em outro terminal:

```powershell
docker compose ps -a
```

É esperado que `ml-trainer` mostre estado `Exited (0)` depois de gerar ou reutilizar o artefato. Para acompanhar a primeira execução:

```powershell
docker compose logs -f ml-trainer ml-inference api mqtt-ingestor
```

O dashboard pode indicar que a análise do modelo ainda está indisponível durante o treinamento. Se o trainer falhar, consulte os logs desse serviço. Artefatos e resultados ficam em `data/ml/training/`; os arquivos são locais e ignorados pelo Git. O experimento aparece em MLflow. Mais detalhes sobre perfis, métricas e limitações estão em [Dados e modelos](../ml/README.md).

Os parâmetros e limites atuais estão em [Métricas e parâmetros](metricas-e-parametros.md), e uma execução de referência com métricas, hashes e interpretação está registrada em [Resultado do experimento](../ml/docs/resultado-experimento.md).

Para abrir o notebook de exploração e gráficos, configure as dependências em [ml/README.md](../ml/README.md#notebook-de-exploração-e-avaliação-visual). A primeira parte gera e prepara sua própria série mockada; a seção de avaliação precisa dos artefatos de treinamento acima.

## 5. Publicar uma leitura pelo MQTT

O fluxo usa um medidor cadastrado e sua chave individual. Na aplicação, abra **Medidores**, cadastre um medidor com número de série exclusivo e copie a chave que é apresentada uma única vez. Em seguida, no PowerShell, publique uma primeira leitura:

```powershell
docker compose run --rm -e DEVICE_SERIAL=AF-MQTT-001 -e DEVICE_KEY=COLE_A_CHAVE -e CUMULATIVE_VOLUME_LITERS=1000 mqtt-publisher
```

Depois publique outra leitura para o mesmo medidor com o volume acumulado maior, por exemplo:

```powershell
docker compose run --rm -e DEVICE_SERIAL=AF-MQTT-001 -e DEVICE_KEY=COLE_A_CHAVE -e CUMULATIVE_VOLUME_LITERS=1000.5 mqtt-publisher
```

A ferramenta publica pelo broker local; o consumidor MQTT encaminha a leitura para a API, que autentica o medidor, valida e persiste o evento. Confira a última comunicação em **Medidores** e a leitura na interface. O delta de volume só pode ser calculado quando há uma leitura anterior compatível. Consulte o [contrato MQTT](contrato-mqtt.md) para o schema e as regras de reenvio.

## 6. Executar o DAG do Airflow

O Airflow é iniciado pelo Compose, mas o DAG é manual. Abra [http://localhost:8080](http://localhost:8080), habilite `aquaflow_mock_telemetry_pipeline` e dispare uma execução. As tarefas encadeadas geram a entrada mockada, verificam sua qualidade e preparam features, rótulos e metadados em `data/ml/`.

O DAG termina na preparação. O treinamento automatizado da aplicação é executado separadamente por `ml-trainer` e não espera uma execução do DAG. Ambos usam os mesmos scripts de geração e preparação; suas pastas de saída são distintas.

## 7. Retreinar os modelos

Para forçar uma nova execução de geração, preparação, comparação e registro no MLflow:

```powershell
docker compose run --build --rm -e ML_RETRAIN_MODEL=true ml-trainer
docker compose restart ml-inference
```

A reinicialização recarrega o artefato recém-treinado pelo worker. Os detalhes da avaliação e do notebook ficam em [Dados e modelos](../ml/README.md).

## 8. Verificar o trajeto MQTT → API → banco

A suíte opcional executa a publicação contra recursos isolados de teste:

```powershell
docker compose -p aquaflow-mqtt-test -f docker-compose.yml -f docker-compose.test.yml --profile test run --build --rm mqtt-e2e
docker compose -p aquaflow-mqtt-test -f docker-compose.yml -f docker-compose.test.yml --profile test down --volumes
```

O segundo comando remove os containers e volumes exclusivos do projeto de teste.

## 9. Encerrar

`Ctrl+C` ou `docker compose down` encerra os serviços e preserva o banco, os dados de ML e os experimentos. `docker compose down --volumes` apaga os volumes nomeados, inclusive banco, estado do broker e estado do Airflow. Os arquivos dentro de `data/` podem permanecer e precisam ser removidos separadamente se você quiser regenerar todos os artefatos locais.

## Limites da demonstração

- Os dados da conta demo e do treinamento são simulados por geradores independentes.
- O modelo classifica cenários definidos artificialmente; seu resultado não confirma vazamento e não foi validado em telemetria real.
- A tela pode exibir dados insuficientes quando uma leitura não tem predecessor adequado ou o intervalo entre amostras é longo.
- O broker configurado no Compose é local e sem TLS para conexão física remota; não conecte hardware fora dessa rede sem preparar autenticação por dispositivo e transporte seguro.
- Airflow e MLflow são interfaces locais de demonstração, não uma implantação de produção.
