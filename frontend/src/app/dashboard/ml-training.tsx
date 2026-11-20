"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { interpolateCurveAtX } from "./dashboard-state.mjs";

type JsonObject = Record<string, unknown>;
type Execution = {
  id: string;
  model: string;
  model_version: string | null;
  started_at: string | null;
  candidate_count: number;
};
type DashboardData = {
  active_model: { key: string; version: string; trained_at: string | null; threshold: number };
  active_execution_id: string | null;
  selected_execution_id: string | null;
  history_available: boolean;
  worker_status: "healthy" | "degraded" | "starting" | "unavailable";
  executions: Execution[];
  active_report: JsonObject;
  report: JsonObject;
};
type CurvePoint = { x: number; y: number };

const MODEL_LABELS: Record<string, string> = {
  decision_tree: "Árvore de decisão",
  dummy_prior: "Baseline",
  knn: "KNN",
  random_forest: "Random Forest",
};
const HISTORY_PREVIEW_LIMIT = 5;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function number(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function text(value: unknown, fallback = "—"): string {
  return typeof value === "string" && value.length ? value : fallback;
}

function modelLabel(value: string): string {
  return MODEL_LABELS[value] ?? value.replaceAll("_", " ");
}

function formatMetric(value: unknown, digits = 3): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("pt-BR", { maximumFractionDigits: digits })
    : "—";
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "Data indisponível";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "Data indisponível"
    : new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function curvePoints(value: unknown, xKey: string, yKey: string): CurvePoint[] {
  const curve = object(value);
  const xValues = curve[xKey];
  const yValues = curve[yKey];
  if (!Array.isArray(xValues) || !Array.isArray(yValues)) return [];
  return xValues.flatMap((x, index) => {
    const y = yValues[index];
    return typeof x === "number" && typeof y === "number" ? [{ x, y }] : [];
  });
}

export function MLTrainingView() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [executionId, setExecutionId] = useState("");
  const executionRef = useRef("");
  const [evaluation, setEvaluation] = useState<"test" | "stress">("test");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [prHover, setPrHover] = useState<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const [rocHover, setRocHover] = useState<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const [trainingJob, setTrainingJob] = useState<{
    id: string;
    status: string;
  } | null>(null);
  const [startingTraining, setStartingTraining] = useState(false);
  const [trainingError, setTrainingError] = useState("");
  const [showFullHistory, setShowFullHistory] = useState(false);
  const [panel, setPanel] = useState<"execution" | "evaluation" | "details" | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const requestRef = useRef(0);
  useEffect(() => {
    if (panel) {
      dialogRef.current?.showModal();
      if (dialogRef.current) dialogRef.current.scrollTop = 0;
    } else dialogRef.current?.close();
  }, [panel]);

  const load = useCallback(async (requestedExecution: string, background = false) => {
    const request = ++requestRef.current;
    if (background) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const query = requestedExecution
        ? `?execution_id=${encodeURIComponent(requestedExecution)}`
        : "";
      const response = await fetch(`/api/backend/ml/training-dashboard${query}`, {
        cache: "no-store",
      });
      const result = (await response.json()) as DashboardData & {
        detail?: { message?: string };
      };
      if (!response.ok)
        throw new Error(result.detail?.message ?? "Não foi possível carregar o painel.");
      if (request !== requestRef.current) return;
      setPrHover(null);
      setRocHover(null);
      setData(result);
      const selected = result.selected_execution_id ?? "";
      executionRef.current = selected;
      setExecutionId(selected);
    } catch (caught) {
      if (request === requestRef.current)
        setError(caught instanceof Error ? caught.message : "Não foi possível carregar o painel.");
    } finally {
      if (request === requestRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load("");
    const timer = window.setInterval(() => void load(executionRef.current, true), 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!trainingJob || !["queued", "running"].includes(trainingJob.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/backend/ml/training-jobs/${trainingJob.id}`, {
          cache: "no-store",
        });
        const result = await response.json();
        if (response.ok) {
          setTrainingJob(result);
          if (result.status === "succeeded") void load("");
        }
      } catch {
        setTrainingError("Não foi possível acompanhar o treinamento.");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [trainingJob, load]);

  async function startTraining() {
    setStartingTraining(true);
    setTrainingError("");
    try {
      const response = await fetch("/api/backend/ml/training-jobs", { method: "POST" });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.detail?.message ?? "Não foi possível iniciar o treinamento.");
      setTrainingJob(result);
    } catch (error) {
      setTrainingError(error instanceof Error ? error.message : "Falha ao iniciar o treinamento.");
    } finally {
      setStartingTraining(false);
    }
  }

  const report = object(data?.report);
  const selectedModel = text(report.selected_model, data?.active_model.key ?? "Modelo");
  const candidates = object(report.candidates);
  const evaluations = object(report.candidate_holdout_evaluation);
  const selectedEvaluations = object(evaluations[selectedModel]);
  const currentMetrics = object(selectedEvaluations[evaluation]);
  const testMetrics = object(object(report.test_evaluation)[selectedModel]);
  const stressMetrics = object(object(report.stress_test_evaluation).selected_model);
  const activeMetrics = evaluation === "stress" ? stressMetrics : testMetrics;
  const displayedMetrics = Object.keys(currentMetrics).length ? currentMetrics : activeMetrics;
  const curves = object(object(report.evaluation_curves)[evaluation]);
  const prCurve = curvePoints(curves.precision_recall, "recall", "precision");
  const rocCurve = curvePoints(curves.roc, "false_positive_rate", "true_positive_rate");
  const candidateChart = useMemo(
    () =>
      Object.entries(candidates).map(([name, value]) => {
        const candidate = object(value);
        const held = object(object(evaluations[name])[evaluation]);
        const test = object(object(evaluations[name]).test ?? object(report.test_evaluation)[name]);
        const stress = object(
          object(evaluations[name]).stress ?? object(report.stress_test_evaluation)[name],
        );
        return {
          key: name,
          name: modelLabel(name),
          ap: typeof held.average_precision === "number" ? held.average_precision : null,
          testAp: typeof test.average_precision === "number" ? test.average_precision : null,
          stressAp: typeof stress.average_precision === "number" ? stress.average_precision : null,
          stressRecall: stress.recall,
          train: candidate.cv_mean_train_average_precision,
          validation: candidate.cv_mean_validation_average_precision,
          gap: candidate.cv_generalization_gap,
          deviation: candidate.cv_validation_average_precision_std,
        };
      }),
    [candidates, evaluations, evaluation, report.test_evaluation, report.stress_test_evaluation],
  );
  const selectedCandidate = object(candidates[selectedModel]);
  const folds = Array.isArray(selectedCandidate.cv_folds)
    ? selectedCandidate.cv_folds.map((item, index) => {
        const fold = object(item);
        return {
          fold: `Fold ${number(fold.fold, index + 1)}`,
          treino: number(fold.train_average_precision),
          validação: number(fold.validation_average_precision),
        };
      })
    : [];
  const matrix = Array.isArray(displayedMetrics.confusion_matrix)
    ? displayedMetrics.confusion_matrix.map((row) =>
        Array.isArray(row) ? row.map((value) => number(value)) : [],
      )
    : [];
  const features = Array.isArray(report.estimator_feature_names)
    ? report.estimator_feature_names.filter((item): item is string => typeof item === "string")
    : [];
  const splitCounts = object(report.split_counts);
  const parameters = object(selectedCandidate.best_parameters);
  const activeReport = object(data?.active_report);
  const activeSelectionScores = object(activeReport.selection_scores);
  const selectedExecution = data?.executions.find((item) => item.id === executionId);
  const metricCards: Array<[string, unknown]> = [
    ["Average Precision", displayedMetrics.average_precision],
    ["Precisão", displayedMetrics.precision],
    ["Recall", displayedMetrics.recall],
    ["F1-score", displayedMetrics.f1],
  ];
  const workerLabels = {
    healthy: "Inferência ativa",
    degraded: "Inferência degradada",
    starting: "Inferência inicializando",
    unavailable: "Inferência indisponível",
  } as const;

  if (loading) {
    return (
      <section className="ml-dashboard-state surface" aria-busy="true" aria-live="polite">
        <span className="ml-state-spinner" aria-hidden="true" />
        <h2>Carregando dados do treinamento</h2>
        <p>Consultando o relatório do modelo e o histórico de execuções.</p>
      </section>
    );
  }
  if (error && !data) {
    return (
      <section className="ml-dashboard-state surface" role="alert">
        <span className="eyebrow">Painel indisponível</span>
        <h2>Não foi possível carregar o treinamento</h2>
        <p>{error}</p>
        <button className="button button--primary" type="button" onClick={() => void load("")}>
          Tentar novamente
        </button>
      </section>
    );
  }
  if (!data || Object.keys(report).length === 0) {
    return (
      <section className="ml-dashboard-state surface">
        <span className="eyebrow">Sem execuções</span>
        <h2>Ainda não há um relatório de treinamento disponível</h2>
        <p>Quando o pipeline concluir uma execução, os resultados aparecerão aqui.</p>
      </section>
    );
  }

  const confusionTotal = matrix.flat().reduce((sum, value) => sum + value, 0);
  const hasEvaluation = Object.keys(displayedMetrics).length > 0;

  return (
    <section className="ml-dashboard" aria-label="Modelos e treinamento">
      <div className="ml-training-action">
        <button
          className="button button--primary"
          type="button"
          onClick={() => void startTraining()}
          disabled={
            startingTraining ||
            (!!trainingJob && ["queued", "running"].includes(trainingJob.status))
          }
        >
          {startingTraining || ["queued", "running"].includes(trainingJob?.status ?? "")
            ? "Treinamento em andamento…"
            : "Treinar novamente"}
        </button>
        <span className="sr-only" role="status" aria-live="polite">
          {startingTraining || trainingJob?.status === "queued" || trainingJob?.status === "running"
            ? "Treinamento em andamento."
            : trainingJob?.status === "succeeded"
              ? "Treinamento concluído e modelo atualizado."
              : ""}
        </span>
        {trainingError && <p role="alert">{trainingError}</p>}
      </div>
      <div className="ml-selection-grid">
        <div className="surface ml-selection-card">
          <div>
            <span>Execução consultada</span>
            <strong>
              {selectedExecution
                ? `${formatDate(selectedExecution.started_at)} · ${modelLabel(selectedExecution.model)}`
                : "Modelo ativo · local"}
            </strong>
          </div>
          <button
            type="button"
            disabled={!data.history_available || refreshing}
            onClick={() => setPanel("execution")}
          >
            Alterar
          </button>
        </div>
        <div className="surface ml-selection-card">
          <div>
            <span>Conjunto avaliado</span>
            <strong>{evaluation === "test" ? "Teste cronológico" : "Estresse"}</strong>
          </div>
          <button type="button" onClick={() => setPanel("evaluation")}>
            Alterar
          </button>
        </div>
      </div>
      <dialog
        ref={dialogRef}
        className={`ml-dialog ${panel === "details" ? "ml-dialog--details" : ""}`}
        aria-labelledby="ml-dialog-title"
        onClick={(event) => {
          if (event.target !== event.currentTarget) return;
          const bounds = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
          )
            setPanel(null);
        }}
        onCancel={() => setPanel(null)}
        onClose={() => setPanel(null)}
      >
        <h2 id="ml-dialog-title" tabIndex={-1} autoFocus>
          {panel === "execution"
            ? "Selecionar execução"
            : panel === "evaluation"
              ? "Selecionar conjunto"
              : "Detalhes do treinamento"}
        </h2>
        {panel === "execution" && (
          <>
            <p>Treinamentos registrados</p>
            {data.executions.map((execution) => (
              <button
                type="button"
                className="ml-dialog-option"
                key={execution.id}
                aria-pressed={execution.id === executionId}
                onClick={() => {
                  setPanel(null);
                  executionRef.current = execution.id;
                  setExecutionId(execution.id);
                  void load(execution.id);
                }}
              >
                <strong>
                  {formatDate(execution.started_at)} · {modelLabel(execution.model)}
                </strong>
                <span>
                  Concluído · {execution.id === data.active_execution_id ? "Modelo ativo · " : ""}
                  {execution.id}
                </span>
              </button>
            ))}
          </>
        )}
        {panel === "evaluation" && (
          <>
            <p>Escolha os dados usados na avaliação</p>
            {(["test", "stress"] as const).map((value) => (
              <button
                type="button"
                className="ml-dialog-option"
                key={value}
                aria-pressed={evaluation === value}
                disabled={value === "stress" && !report.stress_test_evaluation}
                onClick={() => {
                  setEvaluation(value);
                  setPanel(null);
                }}
              >
                <strong>{value === "test" ? "Teste cronológico" : "Avaliação de estresse"}</strong>
                <span>
                  {value === "test"
                    ? "Dados reservados após o período de treinamento"
                    : "Cenários simulados para avaliar a mudança de rotina"}
                </span>
              </button>
            ))}
          </>
        )}
        {panel === "details" && (
          <div className="ml-training-detail">
            <p className="ml-detail-meta">
              {selectedExecution?.id ?? "Artefato local"} ·{" "}
              {formatDate(selectedExecution?.started_at)}
            </p>
            <section className="ml-detail-status">
              <h3>
                Concluído · {modelLabel(selectedModel)} selecionado
                {executionId === data.active_execution_id ? " e ativo" : " nesta execução"}
              </h3>
              <p>
                SHA-256 do modelo: <code>{text(report.model_sha256)}</code>
              </p>
            </section>
            <section className="surface ml-card">
              <h3>Busca e hiperparâmetros</h3>
              <p>
                Busca aleatória com validação temporal · seed{" "}
                {formatMetric(object(report.search).seed, 0)} ·{" "}
                {formatMetric(object(report.search).iterations_per_model, 0)} combinações por modelo
                · {formatMetric(object(report.search).total_candidate_fits, 0)} ajustes em{" "}
                {formatMetric(object(report.search).folds_per_candidate, 0)} folds
              </p>
              <dl className="ml-data-list">
                {Object.entries(parameters).map(([key, value]) => (
                  <div key={key}>
                    <dt>
                      {key === "model__neighbor_fraction"
                        ? "Proporção de vizinhos"
                        : key.replaceAll("_", " ")}
                    </dt>
                    <dd>
                      {key === "model__neighbor_fraction" && typeof value === "number"
                        ? `${formatMetric(value * 100, 1)}% das amostras`
                        : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
              <p>
                Intervalo de {formatMetric(object(report.search).gap_samples, 0)} amostras entre
                treino e validação.{" "}
                {report.feature_policy === "measurements_only_calendar_excluded"
                  ? "Atributos de calendário excluídos."
                  : text(report.feature_policy)}
              </p>
            </section>
            <section className="surface ml-card">
              <h3>Dados e partições</h3>
              <p>
                Treino principal: {formatMetric(splitCounts.train, 0)} · Validação:{" "}
                {formatMetric(splitCounts.validation, 0)} · Teste:{" "}
                {formatMetric(splitCounts.test, 0)} amostras
              </p>
              <p>
                Ajuste final: {formatMetric(report.final_training_sample_count, 0)} amostras · até{" "}
                {formatDate(text(report.final_training_end, ""))}
              </p>
              <p>
                Teste cronológico a partir de {formatDate(text(report.test_start, ""))} ·{" "}
                {text(report.timezone)}
              </p>
              <p>Features: {features.join(" · ").replaceAll("_", " ")}</p>
              <p>Rotinas e rótulos simulados; vazões calibradas em bancada.</p>
            </section>
            <section className="surface ml-card">
              <h3>Artefatos da execução</h3>
              <p>
                Relatório de métricas consultado pela API · versão{" "}
                {selectedExecution?.model_version ?? data.active_model.version}
              </p>
              <dl className="ml-data-list">
                <div className="ml-data-features">
                  <dt>SHA-256 do modelo</dt>
                  <dd>
                    <code>{text(report.model_sha256)}</code>
                  </dd>
                </div>
                <div className="ml-data-features">
                  <dt>SHA-256 dos dados preparados</dt>
                  <dd>
                    <code>{text(report.training_data_sha256)}</code>
                  </dd>
                </div>
                <div className="ml-data-features">
                  <dt>SHA-256 do ajuste final</dt>
                  <dd>
                    <code>{text(report.final_training_data_sha256)}</code>
                  </dd>
                </div>
              </dl>
            </section>
          </div>
        )}
        <button type="button" className="ml-dialog-close" onClick={() => setPanel(null)}>
          {panel === "details" ? "Fechar detalhes" : "Cancelar"}
        </button>
      </dialog>
      {error && (
        <p className="ml-inline-error" role="status">
          A atualização falhou. Os dados exibidos são da última consulta bem-sucedida. {error}
        </p>
      )}
      <p className="ml-selection-hint">
        Execuções: data, modelo e versão · Conjuntos: teste cronológico / estresse
      </p>
      <section className="ml-hero surface">
        <div>
          <span className="ml-hero-label">
            {executionId === data.active_execution_id
              ? "Modelo em operação"
              : "Modelo da execução consultada"}
          </span>
          <h2>{modelLabel(selectedModel)}</h2>
          <p>
            Versão {text(selectedExecution?.model_version, data.active_model.version).slice(0, 12)}{" "}
            · Treinado em{" "}
            {selectedExecution?.started_at
              ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(
                  new Date(selectedExecution.started_at),
                )
              : "data indisponível"}
          </p>
        </div>
        <div className="ml-version">
          <span className="ml-hero-label">
            {data.worker_status === "healthy"
              ? "Worker conectado"
              : workerLabels[data.worker_status]}
          </span>
          <p>
            {typeof parameters.model__neighbor_fraction === "number"
              ? `${formatMetric(selectedEvaluations.effective_neighbors, 0)} vizinhos · votos uniformes`
              : "Parâmetros registrados na execução"}
          </p>
          <button type="button" className="ml-text-action" onClick={() => setPanel("details")}>
            Ver detalhes da execução
          </button>
        </div>
      </section>
      <div className="ml-evaluation-heading">
        <h2>
          {executionId === data.active_execution_id
            ? "Avaliação do modelo ativo"
            : "Avaliação da execução consultada"}
        </h2>
        <span>
          {evaluation === "test" ? "Teste cronológico" : "Estresse"} ·{" "}
          {confusionTotal.toLocaleString("pt-BR")} amostras · limiar{" "}
          {typeof report.threshold === "number"
            ? report.threshold.toLocaleString("pt-BR", { minimumFractionDigits: 2 })
            : "—"}
        </span>
      </div>
      <section
        className="ml-metrics-grid"
        aria-label={`Métricas do conjunto de ${evaluation === "test" ? "teste" : "estresse"}`}
      >
        {metricCards.map(([label, value]) => (
          <article className="surface ml-metric-card" key={String(label)}>
            <span>{label}</span>
            <strong>
              {label === "Precisão" || label === "Recall"
                ? typeof value === "number"
                  ? `${formatMetric(value * 100, 1)}%`
                  : "—"
                : formatMetric(value)}
            </strong>
            <small>
              {label === "Average Precision"
                ? "Qualidade da ordenação das previsões"
                : label === "Precisão"
                  ? "Acertos entre os sinais de anomalia"
                  : label === "Recall"
                    ? "Anomalias simuladas identificadas"
                    : "Equilíbrio entre precisão e recall"}
            </small>
          </article>
        ))}
      </section>
      <section className="ml-content-grid">
        <article className="surface ml-card ml-card--wide">
          <div className="section-heading">
            <div>
              <h2>Comparação de modelos</h2>
              <p className="section-subtitle">
                Artefatos finais · teste cronológico e perfil de estresse
              </p>
            </div>
          </div>
          <div className="ml-candidate-table" role="table" aria-label="Métricas por candidato">
            <div role="row" className="ml-candidate-row ml-candidate-row--head">
              <span>Modelo</span>
              <span>AP · teste</span>
              <span>AP · estresse</span>
              <span>Recall · estresse</span>
              <span>Situação</span>
            </div>
            {[...candidateChart]
              .sort((a, b) =>
                a.key === selectedModel
                  ? -1
                  : b.key === selectedModel
                    ? 1
                    : (b.testAp ?? -1) - (a.testAp ?? -1) || (a.key === "random_forest" ? -1 : 1),
              )
              .map((item) => (
                <div
                  role="row"
                  className={`ml-candidate-row ${item.name === modelLabel(selectedModel) ? "ml-candidate-row--selected" : ""}`}
                  key={item.name}
                >
                  <strong>{item.name}</strong>
                  <span>{formatMetric(item.testAp)}</span>
                  <span>{formatMetric(item.stressAp)}</span>
                  <span>
                    {typeof item.stressRecall === "number"
                      ? `${formatMetric(item.stressRecall * 100, 1)}%`
                      : "—"}
                  </span>
                  <span>
                    {item.key === data.active_model.key
                      ? "Ativo"
                      : item.key === "dummy_prior"
                        ? "Referência"
                        : "Candidato"}
                  </span>
                </div>
              ))}
          </div>
        </article>
        <article className="surface ml-card">
          <div className="section-heading">
            <div>
              <h2>Matriz de confusão</h2>
              <p className="section-subtitle">
                {evaluation === "test" ? "Teste cronológico" : "Estresse"} ·{" "}
                {modelLabel(selectedModel)} · Limiar{" "}
                {typeof report.threshold === "number"
                  ? report.threshold.toLocaleString("pt-BR", { minimumFractionDigits: 2 })
                  : "—"}
              </p>
            </div>
          </div>
          {hasEvaluation && matrix.length === 2 ? (
            <div className="ml-confusion-wrap">
              <div className="ml-confusion-axis">Previsão</div>
              <table className="ml-confusion">
                <thead>
                  <tr>
                    <th aria-label="Real" />
                    <th>Normal</th>
                    <th>Anomalia</th>
                  </tr>
                </thead>
                <tbody>
                  {matrix.map((row, index) => (
                    <tr key={index}>
                      <th>{index === 0 ? "Real: normal" : "Real: anomalia"}</th>
                      {row.map((value, col) => (
                        <td
                          key={col}
                          className={index === col ? "ml-confusion-correct" : "ml-confusion-miss"}
                        >
                          {value.toLocaleString("pt-BR")}
                          <small>
                            {index === 0
                              ? col === 0
                                ? "Verdadeiros negativos"
                                : "Falsos positivos"
                              : col === 0
                                ? "Falsos negativos"
                                : "Verdadeiros positivos"}
                          </small>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="ml-empty">A matriz não está incluída nesta avaliação.</p>
          )}
        </article>
        <article className="surface ml-card">
          <div className="section-heading">
            <div>
              <h2>Desempenho por conjunto</h2>
              <p className="section-subtitle">Average Precision · artefatos finais</p>
            </div>
          </div>
          <div className="ml-bar-legend">
            <span>
              <i />
              Teste cronológico
            </span>
            <span>
              <i />
              Estresse
            </span>
          </div>
          <div className="ml-comparison-bars">
            {[...candidateChart]
              .sort((a, b) =>
                a.key === selectedModel
                  ? -1
                  : b.key === selectedModel
                    ? 1
                    : (b.testAp ?? -1) - (a.testAp ?? -1) || (a.key === "random_forest" ? -1 : 1),
              )
              .map((item) => (
                <div className="ml-comparison-bar-row" key={item.key}>
                  <span>{item.name}</span>
                  <div>
                    {[item.testAp, item.stressAp].map((value, index) => (
                      <div className="ml-comparison-bar-line" key={index}>
                        <div className="ml-bar-track">
                          <i
                            style={{
                              width: `${typeof value === "number" ? Math.max(0, Math.min(1, value)) * 100 : 0}%`,
                              background: index ? "var(--muted)" : "var(--accent)",
                            }}
                          />
                        </div>
                        <small>{formatMetric(value)}</small>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
          </div>
        </article>
        <article className="surface ml-card ml-card--wide ml-generalization-card">
          <div className="section-heading">
            <div>
              <h2>Estabilidade e generalização</h2>
              <p className="section-subtitle">
                Validação temporal · {formatMetric(object(report.search).folds_per_candidate, 0)}{" "}
                folds · Intervalo de {formatMetric(object(report.search).gap_samples, 0)} amostras
                entre treino e validação
              </p>
            </div>
          </div>
          <div className="ml-stability-grid">
            {candidateChart
              .filter((item) => item.key !== "dummy_prior")
              .sort(
                (a, b) =>
                  ["knn", "random_forest", "decision_tree"].indexOf(a.key) -
                  ["knn", "random_forest", "decision_tree"].indexOf(b.key),
              )
              .map((item) => (
                <div key={item.key}>
                  <h3>{item.key === "decision_tree" ? "Árvore de Decisão" : item.name}</h3>
                  <p>
                    AP treino {formatMetric(item.train)}
                    <span className="ml-mini-track">
                      <i
                        style={{
                          width: `${number(item.train) * 100}%`,
                          background: "var(--muted)",
                        }}
                      />
                    </span>
                  </p>
                  <p>
                    AP valid. {formatMetric(item.validation)}
                    <span className="ml-mini-track">
                      <i style={{ width: `${number(item.validation) * 100}%` }} />
                    </span>
                  </p>
                  <small>
                    Gap {formatMetric(item.gap)} · Desvio entre folds {formatMetric(item.deviation)}
                  </small>
                </div>
              ))}
          </div>
        </article>
        <article className="surface ml-card ml-card--wide">
          <div className="section-heading">
            <h2>Histórico de treinamentos</h2>
          </div>
          <div className="ml-candidate-table" role="table" aria-label="Histórico de treinamentos">
            <div className="ml-history-row ml-candidate-row--head" role="row">
              <span>Data</span>
              <span>Execução</span>
              <span>Modelo / Estado</span>
            </div>
            {(showFullHistory
              ? data.executions
              : data.executions.slice(0, HISTORY_PREVIEW_LIMIT)
            ).map((execution) => (
              <button
                type="button"
                className={`ml-history-row ${execution.id === executionId ? "ml-candidate-row--selected" : ""}`}
                key={execution.id}
                onClick={() => {
                  executionRef.current = execution.id;
                  setExecutionId(execution.id);
                  void load(execution.id);
                }}
                disabled={refreshing}
              >
                <span>{formatDate(execution.started_at)}</span>
                <span>{execution.id}</span>
                <span>
                  {modelLabel(execution.model)} ·{" "}
                  {execution.id === data.active_execution_id ? "Ativo" : "Concluído"}
                </span>
              </button>
            ))}
          </div>
          {data.executions.length > HISTORY_PREVIEW_LIMIT && (
            <div className="ml-history-footer">
              <span>
                {showFullHistory
                  ? `${data.executions.length} execuções no histórico`
                  : `${HISTORY_PREVIEW_LIMIT} execuções mais recentes`}
              </span>
              <button
                className="ml-text-action"
                type="button"
                aria-expanded={showFullHistory}
                onClick={() => setShowFullHistory((expanded) => !expanded)}
              >
                {showFullHistory
                  ? "Mostrar menos"
                  : `Ver mais ${data.executions.length - HISTORY_PREVIEW_LIMIT}`}
              </button>
            </div>
          )}
        </article>
        <article className="surface ml-card ml-card--wide">
          <div className="section-heading">
            <h2>Dados e configuração</h2>
          </div>
          <dl className="ml-reference-data">
            <div>
              <dt>Features</dt>
              <dd>Vazão · Delta de volume · Duração entre leituras</dd>
            </div>
            <div>
              <dt>Hiperparâmetros</dt>
              <dd>
                {typeof parameters.model__neighbor_fraction === "number"
                  ? `Vizinhança ${formatMetric(parameters.model__neighbor_fraction * 100, 1)}% · ${formatMetric(selectedEvaluations.effective_neighbors, 0)} vizinhos · Votos uniformes`
                  : Object.entries(parameters)
                      .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`)
                      .join(" · ")}
              </dd>
            </div>
            <div>
              <dt>Ajuste final</dt>
              <dd>
                {formatMetric(report.final_training_sample_count, 0)} amostras · Até{" "}
                {formatDate(text(report.final_training_end, ""))}
              </dd>
            </div>
            <div>
              <dt>Teste cronológico</dt>
              <dd>
                {formatMetric(splitCounts.test, 0)} amostras · Dados a partir de{" "}
                {formatDate(text(report.test_start, ""))}
              </dd>
            </div>
          </dl>
        </article>
        <article className="surface ml-card">
          <div className="section-heading">
            <div>
              <h2>Curva precisão–recall</h2>
              <p className="section-subtitle">
                {modelLabel(selectedModel)} ·{" "}
                {evaluation === "test" ? "Teste cronológico" : "Estresse"} · AP{" "}
                {formatMetric(displayedMetrics.average_precision)}
              </p>
            </div>
            <span className="ml-card-meta">
              AP {formatMetric(displayedMetrics.average_precision)}
            </span>
          </div>
          {prCurve.length ? (
            <div
              className="ml-chart ml-chart--compact ml-roc-interactive"
              role="img"
              aria-label="Curva precisão-recall"
              onMouseLeave={() => setPrHover(null)}
              onMouseMove={(event) => {
                const grid = event.currentTarget.querySelector(".recharts-cartesian-grid");
                if (!grid) return;
                const bounds = grid.getBoundingClientRect();
                if (
                  !bounds.width ||
                  event.clientX < bounds.left ||
                  event.clientX > bounds.right ||
                  event.clientY < bounds.top ||
                  event.clientY > bounds.bottom
                ) {
                  setPrHover(null);
                  return;
                }
                const x = (event.clientX - bounds.left) / bounds.width;
                const y = interpolateCurveAtX(prCurve, x);
                if (y === null) return;
                const container = event.currentTarget.getBoundingClientRect();
                setPrHover({
                  x,
                  y,
                  left: Math.max(
                    0,
                    Math.min(event.clientX - container.left + 12, container.width - 230),
                  ),
                  top: Math.max(0, event.clientY - container.top - 85),
                });
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={prCurve} margin={{ top: 18, right: 24, bottom: 24, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    domain={[0, 1]}
                    ticks={[0, 0.25, 0.5, 0.75, 1]}
                    tickFormatter={(value: number) =>
                      value.toLocaleString("pt-BR", { minimumFractionDigits: 2 })
                    }
                    name="Recall"
                    label={{
                      value: "Recall",
                      position: "insideBottom",
                      offset: -6,
                      fill: "var(--muted)",
                      fontSize: 11,
                    }}
                    tick={{ fill: "var(--muted)", fontSize: 10 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={[0, 1]}
                    ticks={[0, 0.25, 0.5, 0.75, 1]}
                    tickFormatter={(value: number) =>
                      value.toLocaleString("pt-BR", { minimumFractionDigits: 2 })
                    }
                    name="Precisão"
                    tick={{ fill: "var(--muted)", fontSize: 10 }}
                  />
                  <Line
                    type="linear"
                    dataKey="y"
                    name="Precisão"
                    stroke="var(--accent-strong)"
                    strokeWidth={1}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
              {prHover && (
                <div className="ml-roc-tooltip" style={{ left: prHover.left, top: prHover.top }}>
                  <strong>Posição na curva</strong>
                  <span>Recall: {formatMetric(prHover.x, 4)}</span>
                  <span>Precisão: {formatMetric(prHover.y, 4)}</span>
                  <small>Interpolado entre pontos registrados</small>
                </div>
              )}
            </div>
          ) : (
            <p className="ml-empty">
              A curva não está no relatório desta execução. Execute novamente o treinamento para
              produzi-la.
            </p>
          )}
        </article>
        <article className="surface ml-card">
          <div className="section-heading">
            <div>
              <h2>Curva ROC</h2>
              <p className="section-subtitle">
                {modelLabel(selectedModel)} ·{" "}
                {evaluation === "test" ? "Teste cronológico" : "Estresse"} · AUC{" "}
                {formatMetric(curves.roc_auc ?? displayedMetrics.roc_auc)}
              </p>
            </div>
            <span className="ml-card-meta">
              AUC {formatMetric(curves.roc_auc ?? displayedMetrics.roc_auc)}
            </span>
          </div>
          {rocCurve.length ? (
            <div
              className="ml-chart ml-chart--compact ml-roc-interactive"
              role="img"
              aria-label="Curva ROC"
              onMouseLeave={() => setRocHover(null)}
              onMouseMove={(event) => {
                const grid = event.currentTarget.querySelector(".recharts-cartesian-grid");
                if (!grid) return;
                const bounds = grid.getBoundingClientRect();
                if (
                  !bounds.width ||
                  event.clientX < bounds.left ||
                  event.clientX > bounds.right ||
                  event.clientY < bounds.top ||
                  event.clientY > bounds.bottom
                ) {
                  setRocHover(null);
                  return;
                }
                const x = (event.clientX - bounds.left) / bounds.width;
                const y = interpolateCurveAtX(rocCurve, x);
                if (y === null) return;
                const container = event.currentTarget.getBoundingClientRect();
                setRocHover({
                  x,
                  y,
                  left: Math.max(
                    0,
                    Math.min(event.clientX - container.left + 12, container.width - 230),
                  ),
                  top: Math.max(0, event.clientY - container.top - 85),
                });
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rocCurve} margin={{ top: 18, right: 24, bottom: 24, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    domain={[0, 1]}
                    ticks={[0, 0.25, 0.5, 0.75, 1]}
                    tickFormatter={(value: number) =>
                      value.toLocaleString("pt-BR", { minimumFractionDigits: 2 })
                    }
                    name="Falsos positivos"
                    label={{
                      value: "Taxa de falsos positivos",
                      position: "insideBottom",
                      offset: -6,
                      fill: "var(--muted)",
                      fontSize: 11,
                    }}
                    tick={{ fill: "var(--muted)", fontSize: 10 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={[0, 1]}
                    ticks={[0, 0.25, 0.5, 0.75, 1]}
                    tickFormatter={(value: number) =>
                      value.toLocaleString("pt-BR", { minimumFractionDigits: 2 })
                    }
                    name="Verdadeiros positivos"
                    tick={{ fill: "var(--muted)", fontSize: 10 }}
                  />
                  <Line
                    type="linear"
                    dataKey="y"
                    name="Taxa verdadeiro positivo"
                    stroke="var(--accent-strong)"
                    strokeWidth={1}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
              {rocHover && (
                <div className="ml-roc-tooltip" style={{ left: rocHover.left, top: rocHover.top }}>
                  <strong>Posição na curva</strong>
                  <span>Falsos positivos: {formatMetric(rocHover.x, 4)}</span>
                  <span>Verdadeiros positivos: {formatMetric(rocHover.y, 4)}</span>
                  <small>Interpolado entre pontos registrados</small>
                </div>
              )}
            </div>
          ) : (
            <p className="ml-empty">
              A curva não está no relatório desta execução. Execute novamente o treinamento para
              produzi-la.
            </p>
          )}
        </article>
        <article
          className={`surface ml-card ml-card--wide ml-fold-card${!folds.length ? " ml-fold-card--empty" : ""}`}
        >
          <div className="section-heading">
            <div>
              <h2>Validação cruzada por fold</h2>
              <p className="section-subtitle">
                {modelLabel(selectedModel)} · AP por divisão temporal · Escala 0–1
              </p>
            </div>
          </div>
          {!folds.length && (
            <p className="ml-empty">
              Esta execução histórica não registrou os resultados por fold. Eles estarão disponíveis
              em um novo treinamento com o relatório atualizado.
            </p>
          )}
          {folds.length > 0 && (
            <>
              <div className="ml-stability-grid">
                {folds.map((fold) => (
                  <div key={fold.fold}>
                    <h3>{fold.fold}</h3>
                    <p>
                      Treino{" "}
                      <span className="ml-mini-track">
                        <i style={{ width: `${fold.treino * 100}%`, background: "var(--muted)" }} />
                      </span>
                      <strong>{formatMetric(fold.treino)}</strong>
                    </p>
                    <p>
                      Validação{" "}
                      <span className="ml-mini-track">
                        <i style={{ width: `${fold.validação * 100}%` }} />
                      </span>
                      <strong>{formatMetric(fold.validação)}</strong>
                    </p>
                  </div>
                ))}
              </div>
              <p className="ml-fold-summary">
                Média de validação{" "}
                {formatMetric(selectedCandidate.cv_mean_validation_average_precision)} · Desvio
                padrão {formatMetric(selectedCandidate.cv_validation_average_precision_std)} · Gap
                médio treino/validação {formatMetric(selectedCandidate.cv_generalization_gap)}
              </p>
            </>
          )}
        </article>
      </section>
      <aside className="ml-data-notice">
        <h2>Por que o {modelLabel(data.active_model.key)} foi selecionado?</h2>
        <p>
          Maior AP média entre validação temporal e rotina alterada:{" "}
          {formatMetric(activeSelectionScores[data.active_model.key])}.
        </p>
        <p>
          {Object.entries(activeSelectionScores)
            .filter(([name]) => name !== data.active_model.key)
            .sort(
              ([a], [b]) =>
                ["random_forest", "decision_tree", "dummy_prior"].indexOf(a) -
                ["random_forest", "decision_tree", "dummy_prior"].indexOf(b),
            )
            .map(([name, score]) => `${modelLabel(name)}: ${formatMetric(score)}`)
            .join(" · ")}
          .
        </p>
        <p>
          Hiperparâmetros: configuração mais simples dentro de um erro padrão da melhor AP na
          validação cruzada.
        </p>
        <p className="ml-selection-method">
          Teste e estresse avaliam os artefatos após a seleção. A pontuação de seleção usa modelos
          ajustados só no treino; os artefatos finais também incorporam a validação e a rotina
          alterada.
        </p>
      </aside>
      <footer className="ml-reference-footer">
        <p>Série híbrida · Rotinas e rótulos simulados; vazões calibradas em bancada.</p>
        <p>
          Referência visual: execução validada em 20/11/2026. Na aplicação, os dados acompanham a
          execução consultada.
        </p>
      </footer>
      {!data.history_available && (
        <p className="ml-history-note">
          Histórico de execuções do MLflow indisponível no momento. O relatório ativo continua
          visível.
        </p>
      )}
      {data.active_execution_id && executionId !== data.active_execution_id && (
        <p className="ml-history-note">
          Relatório histórico selecionado. Modelo ativo: {data.active_model.key} · versão{" "}
          {data.active_model.version.slice(0, 12)}.
        </p>
      )}
    </section>
  );
}
