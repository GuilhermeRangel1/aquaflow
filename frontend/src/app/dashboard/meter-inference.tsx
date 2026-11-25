import { useEffect, useState } from "react";
import { explainSkippedAnalysis } from "./dashboard-state.mjs";

const attributes: Record<string, [string, string]> = {
  flow_rate_liters_minute: ["Vazão média", "L/min"],
  volume_delta_liters: ["Água no período", "L"],
  elapsed_minutes: ["Duração do período", "min"],
  local_hour_sin: ["Hora local (seno)", ""],
  local_hour_cos: ["Hora local (cosseno)", ""],
  local_weekday_sin: ["Dia da semana (seno)", ""],
  local_weekday_cos: ["Dia da semana (cosseno)", ""],
};

const measures = new Set(["flow_rate_liters_minute", "volume_delta_liters", "elapsed_minutes"]);

function measurement(value: unknown, unit = "", digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return [value.toLocaleString("pt-BR", { maximumFractionDigits: digits }), unit]
    .filter(Boolean)
    .join(" ");
}

function percent(value: number) {
  return value.toLocaleString("pt-BR", { style: "percent", maximumFractionDigits: 1 });
}

function attribute([name, value]: [string, number | string | null]) {
  const [label, unit] = attributes[name] ?? [name.replaceAll("_", " "), ""];
  return (
    <div key={name}>
      <dt>{label}</dt>
      <dd>{measurement(value, unit, measures.has(name) ? 2 : 6)}</dd>
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
  variant: "summary" | "history";
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

  const scored =
    !failed && result?.status === "scored" && result.predicted_anomaly !== null ? result : null;
  const status = failed
    ? "Não foi possível consultar a análise."
    : result === undefined
      ? "Consultando a análise…"
      : result === null
        ? "Esta leitura não tem uma análise própria."
        : scored
          ? scored.predicted_anomaly
            ? "Possível anomalia"
            : "Normal"
          : "Sem dados suficientes";

  const volume = scored?.feature_values.volume_delta_liters;
  const minutes = scored?.feature_values.elapsed_minutes;
  const threshold = scored?.explanation.classification_threshold;

  return (
    <section
      className={variant === "summary" ? "telemetry-analysis" : "telemetry-history-analysis"}
    >
      {variant === "summary" ? (
        <small>Resultado da última análise</small>
      ) : (
        <h4>Análise desta leitura</h4>
      )}
      <p className={variant === "summary" ? "telemetry-analysis-title" : undefined} role="status">
        {status}
      </p>
      {scored && (
        <>
          <div className="telemetry-analysis-explanation">
            {typeof volume === "number" && typeof minutes === "number" && (
              <p>
                {volume === 0 ? (
                  `Não passou água nos ${measurement(minutes, "minutos", 1)} analisados.`
                ) : (
                  <>
                    Passaram cerca de <strong>{measurement(volume, "L")}</strong> em{" "}
                    {measurement(minutes, "minutos", 1)}.
                  </>
                )}
              </p>
            )}
            <p>
              {scored.predicted_anomaly
                ? "Esse uso ficou parecido com os exemplos de consumo fora do comum que o sistema aprendeu. Veja se alguém usou água nesse horário. O resultado não confirma um vazamento."
                : "Esse uso ficou parecido com os exemplos de consumo comum que o sistema aprendeu."}
            </p>
          </div>
          {scored.anomaly_probability !== null && (
            <div className={variant === "summary" ? "telemetry-probability" : undefined}>
              <small>Chance estimada de anomalia</small>
              <strong>{percent(scored.anomaly_probability)}</strong>
              {typeof threshold === "number" && (
                <p>A partir de {percent(threshold)}, o sistema indica possível anomalia.</p>
              )}
            </div>
          )}
        </>
      )}
      {!failed && result && !scored && <p>{explainSkippedAnalysis(result.reason)}</p>}
      {!failed && result && (
        <>
          <p>
            Analisado em{" "}
            <time dateTime={result.inferred_at}>
              {new Date(result.inferred_at).toLocaleString("pt-BR", { timeZone: timezone })}
            </time>
          </p>
          <details className="telemetry-analysis-details">
            <summary>Detalhes técnicos da análise</summary>
            <dl className="telemetry-attribute-grid">
              <div>
                <dt>Leitura analisada</dt>
                <dd>
                  <time dateTime={result.recorded_at}>
                    {new Date(result.recorded_at).toLocaleString("pt-BR", { timeZone: timezone })}
                  </time>
                </dd>
              </div>
              <div>
                <dt>Versão do modelo</dt>
                <dd title={result.model_version}>{result.model_version.slice(0, 12)}</dd>
              </div>
              {Object.entries(result.feature_values).map(attribute)}
            </dl>
            {result.reason && <p>{result.reason}</p>}
          </details>
        </>
      )}
    </section>
  );
}
