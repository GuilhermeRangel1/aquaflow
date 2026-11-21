"use client";

import { useEffect, useState } from "react";

type Classification = {
  normal_liters: number;
  flagged_liters: number;
  unclassified_liters: number;
};

const liters = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

export function ConsumptionClassificationCard({
  propertyId,
  days,
  request,
}: {
  propertyId: string;
  days: number;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
}) {
  const [data, setData] = useState<Classification>();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void request<Classification>(
      `properties/${propertyId}/consumption-classification?days=${days}`,
      { signal: controller.signal },
    )
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [days, propertyId, request]);

  const normal = data?.normal_liters ?? 0;
  const flagged = data?.flagged_liters ?? 0;
  const unclassified = data?.unclassified_liters ?? 0;
  const total = normal + flagged + unclassified;
  const normalEnd = total ? (normal / total) * 100 : 0;
  const flaggedEnd = total ? ((normal + flagged) / total) * 100 : 0;
  const rows = [
    { label: "Dentro do padrão", value: normal, color: "var(--accent-strong)" },
    { label: "Vale verificar", value: flagged, color: "var(--warm)" },
    { label: "Sem análise", value: unclassified, color: "var(--line)" },
  ];

  return (
    <article className="surface chart-card water-cost-card">
      <div className="section-heading">
        <h2>Consumo dentro e fora do padrão</h2>
        <span>{days === 1 ? "Últimas 24 horas" : `Últimos ${days} dias`}</span>
      </div>
      {failed ? (
        <p role="status">Não foi possível carregar a análise do consumo.</p>
      ) : !data ? (
        <p role="status">Carregando análise do consumo…</p>
      ) : !total ? (
        <p>Nenhum consumo registrado no período.</p>
      ) : (
        <>
          <div className="classified-consumption">
            <div
              className="classified-consumption-ring"
              aria-hidden="true"
              style={{
                background: `conic-gradient(var(--accent-strong) 0 ${normalEnd}%, var(--warm) ${normalEnd}% ${flaggedEnd}%, var(--line) ${flaggedEnd}% 100%)`,
              }}
            >
              <div>
                <strong>{liters.format(total)} L</strong>
                <span>Total registrado</span>
              </div>
            </div>
            <dl>
              {rows.map(({ label, value, color }) => (
                <div key={label}>
                  <dt>
                    <i aria-hidden="true" style={{ background: color }} />
                    {label}
                  </dt>
                  <dd>{liters.format(value)} L</dd>
                </div>
              ))}
            </dl>
          </div>
          <small>
            “Vale verificar” indica água que passou em períodos sinalizados. Um aviso por si só não
            confirma vazamento.
          </small>
        </>
      )}
    </article>
  );
}
