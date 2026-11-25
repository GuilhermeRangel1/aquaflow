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

const count = new Intl.NumberFormat("pt-BR");

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
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (paused) return;
    let cancelled = false;
    let timer: number | undefined;
    async function refresh() {
      try {
        const result = await load<SystemHealth>(`properties/${propertyId}/dashboard-health`);
        if (!cancelled) {
          setHealth(result);
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

  const items = health && [
    {
      label: "Recebimento das leituras",
      status: {
        connected: "Funcionando",
        disconnected: "Sem conexão",
        unavailable: "Estado não disponível",
      }[health.ingestion.mqtt_status],
      detail: `Leituras desta casa em 24 horas: ${count.format(health.ingestion.readings_last_24h)}. Mensagens recusadas em todo o sistema desde que ele iniciou: ${count.format(health.ingestion.mqtt_messages_rejected)}.`,
    },
    {
      label: "Análise automática",
      status: {
        healthy: "Funcionando",
        degraded: "Com falhas recentes",
        unavailable: "Indisponível",
      }[health.model_pipeline.status],
      detail: `Em 24 horas: ${count.format(health.model_pipeline.scored_inferences_last_24h)} com resultado, sendo ${count.format(health.model_pipeline.positive_predictions_last_24h)} de possível anomalia. Sem dados suficientes: ${count.format(health.model_pipeline.skipped_inferences_last_24h)}.`,
    },
    {
      label: "Regras fixas de consumo",
      status: "Ativas",
      detail: `Avisos em 24 horas: ${count.format(health.rules_fallback.alerts_last_24h)}. Elas funcionam mesmo se a análise automática parar.`,
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
