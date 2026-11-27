"use client";

import { useEffect, useState } from "react";

type SystemHealth = {
  checked_at: string;
  ingestion: {
    readings_last_24h: number;
    mqtt_status: "connected" | "disconnected" | "unavailable";
    mqtt_messages_rejected: number;
  };
  model_pipeline: {
    status: "healthy" | "degraded" | "unavailable";
    failed_batches: number;
    scored_inferences_last_24h: number;
    skipped_inferences_last_24h: number;
    positive_predictions_last_24h: number;
  };
  rules_fallback: { alerts_last_24h: number };
};

type InferencePage = {
  items: {
    predicted_anomaly: boolean | null;
    inferred_at: string;
    recorded_at: string;
    device_name: string;
  }[];
  cursor: string | null;
  has_more: boolean;
};

type Positive = { recorded_at: string; device_name: string };

const count = new Intl.NumberFormat("pt-BR");

/** Finds the newest "possible anomaly" of the last 24 hours, so the count has a when and where. */
async function newestPositive(
  load: <T>(path: string) => Promise<T>,
  propertyId: string,
  since: number,
): Promise<Positive | null> {
  const params = new URLSearchParams({ limit: "100" });
  for (let page = 0; page < 4; page += 1) {
    const result = await load<InferencePage>(`properties/${propertyId}/ml-inferences?${params}`);
    for (const item of result.items) {
      if (Date.parse(item.inferred_at) < since) return null;
      if (item.predicted_anomaly) return item;
    }
    if (!result.has_more || !result.cursor) return null;
    params.set("cursor", result.cursor);
  }
  return null;
}

export function SystemStatusCard({
  propertyId,
  timezone,
  paused,
  load,
}: {
  propertyId: string;
  timezone: string;
  paused: boolean;
  load: <T>(path: string) => Promise<T>;
}) {
  const [health, setHealth] = useState<SystemHealth>();
  const [positive, setPositive] = useState<Positive | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (paused) return;
    let cancelled = false;
    let timer: number | undefined;
    async function refresh() {
      try {
        const result = await load<SystemHealth>(`properties/${propertyId}/dashboard-health`);
        const latest =
          result.model_pipeline.positive_predictions_last_24h > 0
            ? await newestPositive(
                load,
                propertyId,
                Date.parse(result.checked_at) - 24 * 3_600_000,
              ).catch(() => null)
            : null;
        if (!cancelled) {
          setHealth(result);
          setPositive(latest);
          setFailed(false);
        }
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) timer = window.setTimeout(refresh, 30_000);
      }
    }
    void refresh();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [load, paused, propertyId]);

  const positives = health?.model_pipeline.positive_predictions_last_24h ?? 0;
  const rejected = health?.ingestion.mqtt_messages_rejected ?? 0;
  const items = health && [
    {
      label: "Recebimento de leituras",
      status: {
        connected: "Funcionando",
        disconnected: "Sem conexão",
        unavailable: "Estado não disponível",
      }[health.ingestion.mqtt_status],
      detail: [
        "O sistema está pronto para receber leituras de todos os medidores. Se um medidor parar de enviar, o problema costuma estar nele, na energia ou no Wi-Fi.",
        `Leituras desta casa nas últimas 24 horas: ${count.format(health.ingestion.readings_last_24h)}.`,
        rejected > 0 &&
          `${count.format(rejected)} ${rejected === 1 ? "mensagem chegou com problema e foi descartada" : "mensagens chegaram com problema e foram descartadas"}.`,
      ]
        .filter(Boolean)
        .join(" "),
    },
    {
      label: "Análise automática",
      status: {
        healthy: "Funcionando",
        degraded: "Com falhas recentes",
        unavailable: "Indisponível",
      }[health.model_pipeline.status],
      detail: [
        `Analisou ${count.format(health.model_pipeline.scored_inferences_last_24h)} períodos nas últimas 24 horas.`,
        positives === 0
          ? "Nenhum deles teve uso fora do comum."
          : `${count.format(positives)} ${positives === 1 ? "teve" : "tiveram"} uso fora do comum.`,
        positive &&
          `${positives === 1 ? "Foi" : "O mais recente foi"} em ${new Date(
            positive.recorded_at,
          ).toLocaleString("pt-BR", {
            timeZone: timezone,
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}, no ${positive.device_name}.`,
        positives > 0 &&
          "Um aviso só aparece em Alertas quando dois períodos seguidos ficam fora do comum.",
        health.model_pipeline.skipped_inferences_last_24h > 0 &&
          `Sem dados suficientes: ${count.format(health.model_pipeline.skipped_inferences_last_24h)}.`,
      ]
        .filter(Boolean)
        .join(" "),
    },
    {
      label: "Regras fixas de consumo",
      status: "Ativas",
      detail: `Avisos nas últimas 24 horas: ${count.format(health.rules_fallback.alerts_last_24h)}. Elas vigiam, por exemplo, água que não para de passar e funcionam mesmo se a análise automática parar.`,
    },
  ];

  return (
    <section className="surface telemetry-card" aria-label="Funcionamento do sistema">
      <div className="telemetry-toolbar">
        <h2>Funcionamento do sistema</h2>
        {health && (
          <small>
            Conferido às{" "}
            {new Date(health.checked_at).toLocaleTimeString("pt-BR", { timeZone: timezone })}
          </small>
        )}
      </div>
      {failed && <p role="status">Não foi possível conferir o funcionamento agora.</p>}
      {!health && !failed && <p role="status">Conferindo o funcionamento…</p>}
      {items && (
        <dl className="telemetry-attribute-grid telemetry-system-grid">
          {items.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.status}</dd>
              <dd className="telemetry-system-detail">{item.detail}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
