import { useEffect, useState } from "react";
import { explainSkippedAnalysis } from "./dashboard-state.mjs";

function measurement(value: unknown, unit = "", digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return [value.toLocaleString("pt-BR", { maximumFractionDigits: digits }), unit]
    .filter(Boolean)
    .join(" ");
}

function percent(value: number) {
  return value.toLocaleString("pt-BR", { style: "percent", maximumFractionDigits: 1 });
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

/** Technical details in plain words. The model's sine/cosine time features become the day and time. */
function PlainDetails({ result, timezone }: { result: Inference; timezone?: string }) {
  const end = new Date(result.recorded_at);
  const minutes = result.feature_values.elapsed_minutes;
  const volume = result.feature_values.volume_delta_liters;
  const flow = result.feature_values.flow_rate_liters_minute;
  const time = (date: Date) =>
    date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: timezone });
  const start =
    typeof minutes === "number" && Number.isFinite(minutes)
      ? new Date(end.getTime() - minutes * 60_000)
      : null;
  const weekday = end.toLocaleDateString("pt-BR", { weekday: "long", timeZone: timezone });

  return (
    <details className="telemetry-analysis-details">
      <summary>Detalhes da análise</summary>
      <dl className="telemetry-attribute-grid">
        <div>
          <dt>Período analisado</dt>
          <dd>
            {start
              ? `${time(start)} às ${time(end)} (${measurement(minutes, "minutos", 1)})`
              : `Até ${time(end)}`}
          </dd>
        </div>
        <div>
          <dt>Água que passou</dt>
          <dd>{measurement(volume, "litros")}</dd>
        </div>
        <div>
          <dt>Média por minuto</dt>
          <dd>{measurement(flow, "litros por minuto")}</dd>
        </div>
        <div>
          <dt>Dia e horário considerados</dt>
          <dd>
            {weekday}, {time(end)}
          </dd>
        </div>
      </dl>
      <p>
        O sistema compara a água que passou nesse período com exemplos de uso comum e fora do comum.
        Ele também leva em conta o dia da semana e o horário.
      </p>
      <p className="telemetry-analysis-version">
        Versão do modelo, para a equipe técnica:{" "}
        <span title={result.model_version}>{result.model_version.slice(0, 12)}</span>
      </p>
    </details>
  );
}

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
  const probability = scored?.anomaly_probability ?? null;

  const explanation = scored && (
    <>
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
    </>
  );
  const skipped = !failed && result && !scored && <p>{explainSkippedAnalysis(result.reason)}</p>;
  const analyzedAt = !failed && result && (
    <p className={variant === "summary" ? "telemetry-analysis-time" : undefined}>
      Analisado em{" "}
      <time dateTime={result.inferred_at}>
        {new Date(result.inferred_at).toLocaleString("pt-BR", { timeZone: timezone })}
      </time>
    </p>
  );
  const details = !failed && result && <PlainDetails result={result} timezone={timezone} />;

  if (variant === "summary") {
    return (
      <section className="telemetry-analysis" aria-label="Resultado da última análise">
        <small>Resultado da última análise</small>
        <p className="telemetry-analysis-title" role="status">
          {status}
        </p>
        {(explanation || skipped || probability !== null) && (
          <div className="telemetry-analysis-panel">
            {(explanation || skipped) && (
              <div className="telemetry-analysis-section">
                <h3>O que aconteceu</h3>
                {explanation}
                {skipped}
              </div>
            )}
            {probability !== null && (
              <div className="telemetry-analysis-section">
                <h3>Chance estimada de anomalia</h3>
                <strong className="telemetry-analysis-chance">{percent(probability)}</strong>
                <div className="telemetry-chance-meter" aria-hidden="true">
                  <span
                    className={
                      scored?.predicted_anomaly
                        ? "telemetry-chance-fill telemetry-chance-fill-warm"
                        : "telemetry-chance-fill"
                    }
                    style={{ width: `${Math.min(Math.max(probability, 0), 1) * 100}%` }}
                  />
                  {typeof threshold === "number" && (
                    <i style={{ left: `${Math.min(Math.max(threshold, 0), 1) * 100}%` }} />
                  )}
                </div>
                {typeof threshold === "number" && (
                  <p>A partir de {percent(threshold)}, o sistema indica possível anomalia.</p>
                )}
              </div>
            )}
          </div>
        )}
        <div className="telemetry-analysis-footer">
          {analyzedAt}
          {details}
        </div>
      </section>
    );
  }

  return (
    <section className="telemetry-history-analysis">
      <h4>Análise desta leitura</h4>
      <p role="status">{status}</p>
      {scored && <div className="telemetry-analysis-explanation">{explanation}</div>}
      {probability !== null && (
        <div>
          <small>Chance estimada de anomalia</small>
          <strong>{percent(probability)}</strong>
          {typeof threshold === "number" && (
            <p>A partir de {percent(threshold)}, o sistema indica possível anomalia.</p>
          )}
        </div>
      )}
      {skipped}
      {analyzedAt}
      {details}
    </section>
  );
}
