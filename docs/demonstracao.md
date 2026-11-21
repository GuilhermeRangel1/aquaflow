# Demonstração e execução local

Este guia explica como iniciar o protótipo, observar o que cada processo está fazendo e demonstrar os caminhos principais sem hardware físico. A demonstração usa uma conta local e dados sintéticos; não representa medição real de uma residência.

## 1. Pré-requisitos

- Docker Desktop instalado, aberto e com Docker Compose v2 disponível.
- Memória suficiente para PostgreSQL, frontend, API, treinamento e Airflow. A primeira inicialização pode levar mais tempo porque imagens e artefatos de ML ainda precisam ser preparados.
- Portas locais `3000`, `5000`, `5432`, `8000`, `8080` e `1883` disponíveis. O ESP32 acessa o broker MQTT pela porta `1883` no IP local do computador.

Na raiz do repositório, opcionalmente copie `.env.example` para `.env` caso queira alterar senha do banco, JWT, conta demonstrativa ou credenciais MQTT. Os padrões são somente para desenvolvimento local.

## 2. Subir a aplicação

Execute um único comando:

```powershell
docker compose up --build
```

O Compose constrói e inicia os serviços integrados. Na ordem lógica:

1. PostgreSQL fica pronto.
2. O serviço `demo-data` gera a série híbrida com a calibração do treino. A API aplica as migrations e grava esse histórico no PostgreSQL da conta demo.
3. Broker MQTT e consumidor ficam disponíveis; o consumidor encaminha mensagens para a API HTTP.
4. MLflow fica disponível para registrar experimentos.
5. Se não houver artefato treinado, `ml-trainer` gera a série híbrida calibrada em bancada, analisa, prepara e compara os modelos. Ele termina normalmente ao concluir.
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
E-mail: admin@admin.com
Senha: admin123
Propriedade: Casa da Administração
```

## 3. O que aparece na conta demo

Selecione **Casa da Administração** para abrir o **Medidor principal**. O histórico usa as mesmas vazões e volumes da série de treino, com as datas deslocadas para o período da instalação. Na atualização, a API remove os medidores e alertas identificados como exemplos legados. Telemetria de dispositivos físicos é preservada. Para mostrar o ESP32 ao vivo, cadastre um medidor físico separado na propriedade híbrida com intervalo esperado de 30 segundos.

Os registros exibidos nessa propriedade são dados de demonstração, não mensagens transmitidas por um medidor físico. As regras e o worker geram alertas a partir das leituras e janelas avaliadas. As previsões do modelo são experimentais e aparecem separadas dos detectores por regras.

## 4. Acompanhar inicialização e treinamento

Para ver o estado dos serviços em outro terminal:

```powershell
docker compose ps -a
```

É esperado que `ml-trainer` mostre estado `Exited (0)` depois de gerar ou reutilizar o artefato. Para acompanhar a primeira execução:

```powershell
docker compose logs -f ml-trainer ml-inference api mqtt-ingestor
```

O dashboard pode indicar que a análise do modelo ainda está indisponível durante o treinamento. Se o trainer falhar, consulte os logs desse serviço. Artefatos e resultados ficam em `data/ml/training-bench-v2/`; os arquivos são locais e ignorados pelo Git. O experimento aparece em MLflow. Mais detalhes sobre perfis, métricas e limitações estão em [Dados e modelos](../ml/README.md).

### Roteiro para a apresentação

1. Acione o DAG híbrido no Airflow e mostre as etapas de geração, análise, preparação e treino do candidato.
2. Abra o experimento `aquaflow-hybrid-airflow` no MLflow e expanda uma execução por modelo para mostrar as tentativas de busca, as métricas por divisão temporal e a combinação escolhida.
3. Selecione no dashboard a propriedade do ESP32. Passe água pelo sensor e confirme a chegada da leitura via MQTT e sua persistência pela API.
4. Mantenha a coleta até fechar uma janela válida de cinco minutos com uma leitura anterior disponível como referência. Consulte `GET /api/v1/properties/{property_id}/ml-inferences` com autenticação e compare os identificadores das leituras com os resultados. O dashboard atual mostra avisos gerados por previsões positivas.
5. Apresente a diferença entre o desempenho no teste padrão e no perfil de estresse. Se usar um publicador de teste, identifique essa etapa como simulação e registre o ensaio físico como pendente.

Os parâmetros e limites atuais estão em [Métricas e parâmetros](metricas-e-parametros.md), e uma execução de referência com métricas, hashes e interpretação está registrada em [Resultado do experimento](../ml/docs/resultado-experimento.md).

As evidências da execução integrada de 20/11/2026 estão em [Validação da integração](validacao-integracao.md).

Para abrir o notebook de exploração e gráficos, configure as dependências em [ml/README.md](../ml/README.md#notebook-de-exploração-e-avaliação-visual). A primeira parte gera e prepara sua própria série híbrida; a seção de avaliação precisa dos artefatos de treinamento acima.

## 5. Demonstrar a ingestão com o ESP32

Cadastre o ESP32 em **Medidores**, copie a chave do dispositivo e configure o firmware conforme o [guia de montagem](../firmware/aquaflow-esp32/README.md). Use a cadência esperada de 30 segundos. Depois da próxima publicação, recarregue **Medidores** para conferir a leitura salva pela API.

## 6. Executar o DAG do Airflow

Abra [http://localhost:8080](http://localhost:8080), habilite `aquaflow_hybrid_telemetry_pipeline` e dispare uma execução. A última tarefa treina com as features, rótulos e metadados gerados pelas tarefas anteriores. O candidato e o relatório ficam em `data/ml/airflow/<execução>/training/` e o MLflow registra o experimento. A aplicação segue usando o artefato inicial até uma ativação explícita.

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

- O histórico inicial e o treinamento usam a mesma série híbrida.
- O modelo classifica cenários definidos artificialmente; seu resultado não confirma vazamento e não foi validado em telemetria real.
- A tela pode exibir dados insuficientes quando uma leitura não tem predecessor adequado ou o intervalo entre amostras é longo.
- O broker configurado no Compose é local e sem TLS para conexão física remota; não conecte hardware fora dessa rede sem preparar autenticação por dispositivo e transporte seguro.
- Airflow e MLflow são interfaces locais de demonstração, não uma implantação de produção.
