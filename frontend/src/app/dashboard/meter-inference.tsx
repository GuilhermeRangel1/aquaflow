import { useEffect, useState } from "react";

const attributes: Record<string, [string, string]> = {
  flow_rate_liters_minute: ["Vazão", "L/min"],
  volume_delta_liters: ["Volume no intervalo", "L"],
  elapsed_minutes: ["Duração do intervalo", "min"],
  local_hour_sin: ["Hora local (seno)", ""],
  local_hour_cos: ["Hora local (cosseno)", ""],
  local_weekday_sin: ["Dia da semana (seno)", ""],
  local_weekday_cos: ["Dia da semana (cosseno)", ""],
};

function measurement(value: unknown, unit = "") {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return [value.toLocaleString("pt-BR", { maximumFractionDigits: 6 }), unit]
    .filter(Boolean)
    .join(" ");
}

const measures = new Set(["flow_rate_liters_minute", "volume_delta_liters", "elapsed_minutes"]);

function attribute([name, value]: [string, number | string | null]) {
  const [label, unit] = attributes[name] ?? [name.replaceAll("_", " "), ""];
  return (
    <div key={name}>
      <dt>{label}</dt>
      <dd>{measurement(value, unit)}</dd>
    </div>
  );
}

type Inference = {
  status: "scored" | "skipped";
  predicted_anomaly: boolean | null;
  anomaly_probability: number | null;
  model_version: string;
  inferred_at: string;
  recorded_at: string;
  reason: string;
  feature_values: Record<string, number | string | null>;
  explanation: Record<string, unknown>;
};

export function MeterInference({
  readingId,
  deviceId,
  propertyId,
  load,
  paused = false,
  variant,
  timezone,
}: {
  readingId: string;
  deviceId: string;
  propertyId: string;
  load: <T>(path: string) => Promise<T>;
  paused?: boolean;
  variant?: "summary" | "history";
  timezone?: string;
}) {
  const [result, setResult] = useState<Inference | null | undefined>(undefined);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (paused) return;
    let cancelled = false;
    let timer: number | undefined;
    const query = new URLSearchParams({ device_id: deviceId, reading_id: readingId, limit: "1" });
    async function refresh() {
      try {
        const response = await load<{ items: Inference[] }>(
          `properties/${propertyId}/ml-inferences?${query}`,
        );
        if (!cancelled) {
          setResult(response.items[0] ?? null);
          setFailed(false);
        }
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) timer = window.setTimeout(refresh, 5_000);
      }
    }
    void refresh();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [deviceId, load, paused, propertyId, readingId]);

  const status = failed
    ? "Consulta de inferência indisponível."
    : result === undefined
      ? "Consultando inferência…"
      : result === null
        ? "Sem resultado registrado para esta leitura."
        : result.status === "skipped" || result.predicted_anomaly === null
          ? "Leitura não avaliada."
          : result.predicted_anomaly
            ? "Possível anomalia."
            : "Comportamento normal.";

  const Panel = variant === "history" ? "div" : "details";
  return (
    <section
      className={
        variant === "summary"
          ? "telemetry-analysis"
          : variant === "history"
            ? "telemetry-history-analysis"
            : "surface settings-card"
      }
    >
      {variant === "summary" ? (
        <small>Última análise do modelo</small>
      ) : (
        <h3>
          {variant === "history" ? "Inferência associada à leitura" : "Inferência da leitura"}
        </h3>
      )}
      {variant === "history" ? (
        <dl className="telemetry-attribute-grid telemetry-reading-fields">
          <div>
            <dt>Resultado</dt>
            <dd role="status">{status}</dd>
          </div>
          {!failed && result && (
            <>
              <div>
                <dt>Analisada em</dt>
                <dd>
                  <time dateTime={result.inferred_at}>
                    {new Date(result.inferred_at).toLocaleString("pt-BR", { timeZone: timezone })}
                  </time>
                </dd>
              </div>
              {result.status === "scored" && result.anomaly_probability !== null && (
                <div>
                  <dt>Probabilidade estimada de anomalia</dt>
                  <dd>
                    {result.anomaly_probability.toLocaleString("pt-BR", {
                      style: "percent",
                      maximumFractionDigits: 1,
                    })}
                  </dd>
                </div>
              )}
              {result.status === "scored" &&
                typeof result.explanation.classification_threshold === "number" && (
                  <div>
                    <dt>Limiar de anomalia</dt>
                    <dd>{measurement(result.explanation.classification_threshold * 100, "%")}</dd>
                  </div>
                )}
              <div>
                <dt>Versão do modelo</dt>
                <dd title={result.model_version}>{result.model_version.slice(0, 12)}</dd>
              </div>
            </>
          )}
        </dl>
      ) : (
        <p className={variant === "summary" ? "telemetry-analysis-title" : undefined} role="status">
          {status}
        </p>
      )}
      {!failed && result && (
        <>
          {variant !== "history" &&
            result.status === "scored" &&
            result.anomaly_probability !== null && (
              <div
                className={
                  variant === "summary" ? "telemetry-probability" : "telemetry-reading-probability"
                }
              >
                <small>Probabilidade estimada de anomalia</small>
                <strong>
                  {result.anomaly_probability.toLocaleString("pt-BR", {
                    style: "percent",
                    maximumFractionDigits: 1,
                  })}
                </strong>
                {typeof result.explanation.classification_threshold === "number" && (
                  <p>
                    Limiar de anomalia:{" "}
                    {measurement(result.explanation.classification_threshold * 100, "%")}
                  </p>
                )}
              </div>
            )}
          {variant !== "history" && (
            <>
              <p title={result.model_version}>
                Versão do modelo:{" "}
                {variant ? result.model_version.slice(0, 12) : result.model_version}
              </p>
              <p>
                Leitura de{" "}
                <time dateTime={result.recorded_at}>
                  {new Date(result.recorded_at).toLocaleString("pt-BR", { timeZone: timezone })}
                </time>
                {" · Analisada em "}
                <time dateTime={result.inferred_at}>
                  {new Date(result.inferred_at).toLocaleString("pt-BR", { timeZone: timezone })}
                </time>
              </p>
            </>
          )}
          <Panel className="telemetry-analysis-details">
            {variant !== "history" && (
              <summary>
                {variant === "summary"
                  ? "Ver detalhes da análise"
                  : "Como o modelo analisou a leitura"}
              </summary>
            )}
            {result.status === "skipped" && result.reason && <p>{result.reason}</p>}
            {variant === "history" && <h4>Atributos utilizados</h4>}
            <dl className="telemetry-attribute-grid">
              {Object.entries(result.feature_values)
                .filter(([name]) => measures.has(name))
                .map(attribute)}
            </dl>
            {Object.keys(result.feature_values).some((name) => !measures.has(name)) && (
              <div className="telemetry-technical-attributes">
                <h4>Atributos técnicos</h4>
                <dl className="telemetry-attribute-grid">
                  {Object.entries(result.feature_values)
                    .filter(([name]) => !measures.has(name))
                    .map(attribute)}
                </dl>
              </div>
            )}
            {result.status === "scored" && result.predicted_anomaly !== null && (
              <div className="telemetry-analysis-explanation">
                <h4>O que esse resultado significa?</h4>
                <p>
                  {result.predicted_anomaly
                    ? "O modelo sinalizou uma possível anomalia nesse intervalo. Confira se havia alguma atividade que explique o consumo nesse intervalo. O resultado não confirma um vazamento."
                    : "O modelo classificou o consumo desse intervalo como normal. Quando a estimativa atinge o limiar, a leitura é sinalizada para verificação."}
                </p>
              </div>
            )}
          </Panel>
        </>
      )}
    </section>
  );
}
