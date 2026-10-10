# Pipeline de preparação e análise

O DAG `aquaflow_mock_telemetry_pipeline` está em `ml/airflow/dags/`. Ele é executado manualmente, com seed e janela fixas, em três tarefas encadeadas:

1. **Geração:** grava a entrada em `data/ml/raw/mock_readings.csv`.
2. **Análise e validação:** verifica schema, timestamps, UUIDs, valores plausíveis e rótulos; produz `data/ml/analysis/eda_report.json` com cobertura, lacunas, duplicatas, faixa temporal, contagem por cenário e estatísticas descritivas.
3. **Preparação:** produz `features.csv`, `labels.csv` e `preparation_manifest.json` em `data/ml/prepared/`.

Os valores simulados mantêm suas unidades originais. O horário é codificado em ciclos de seno e cosseno para hora do dia e dia da semana, em UTC. UUID, timestamp e serial acompanham as features para rastreabilidade, mas são metadados e não devem ser usados como variáveis de entrada do modelo. Os rótulos ficam em arquivo separado para reduzir risco de vazamento do alvo.

Horários sem leitura não são preenchidos com zeros nem interpolados: são contados no relatório e excluídos das tabelas de observações. Normalização, escala ajustada aos dados e codificação de categorias ficam para depois da definição da tarefa e da separação temporal de treino/validação. Ajustar essas transformações antes da divisão poderia vazar informação da validação.

O modo standalone e o SQLite persistido do Airflow são apenas para desenvolvimento local. O Compose padrão inicia o Airflow em `http://localhost:8080`, sem login e vinculado ao loopback da máquina. A execução Airflow e seu banco de metadados ainda precisam de uma configuração mais robusta caso o ambiente deixe de ser uma demonstração local.
