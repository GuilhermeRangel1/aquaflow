"use client";

import { useEffect, useState } from "react";

type Month = { month: string; liters: number; water_cost_cents: number };
type Estimate = { current_month: string; months: Month[] };

const MINIMUM_BAND_LITERS = 10_000;

const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const volume = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const monthName = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function WaterCostCard({
  propertyId,
  request,
}: {
  propertyId: string;
  request: <T>(path: string, init?: RequestInit) => Promise<T>;
}) {
  const [estimate, setEstimate] = useState<Estimate>();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void request<Estimate>(`properties/${propertyId}/water-cost-estimate`, {
      signal: controller.signal,
    })
      .then((result) => {
        if (!controller.signal.aborted) setEstimate(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [propertyId, request]);

  const current = estimate?.months.find((month) => month.month === estimate.current_month);
  const months = estimate?.months ?? [];
  const max = Math.max(1, ...months.map((month) => month.water_cost_cents));

  return (
    <article
      className="surface chart-card water-cost-card"
      aria-label="Estimativa de custo de água"
    >
      <h2>Quanto vou pagar pela água?</h2>
      {failed ? (
        <p role="status">Não foi possível carregar a estimativa.</p>
      ) : !estimate ? (
        <p role="status">Carregando estimativa…</p>
      ) : current ? (
        <>
          <span>Recife · tarifa residencial de referência da Compesa</span>
          <strong className="water-cost-value">
            {currency.format(current.water_cost_cents / 100)}
          </strong>
          <p>Estimativa do mês até hoje, sem esgoto ou outras cobranças.</p>
          <p>
            <strong>{volume.format(current.liters)} L</strong> registrados no mês.
            {current.liters < MINIMUM_BAND_LITERS &&
              ` Restam ${volume.format(MINIMUM_BAND_LITERS - current.liters)} L até começar a cobrança adicional.`}
          </p>
        </>
      ) : (
        <p>Sem leituras suficientes para estimar o custo deste mês.</p>
      )}
      {estimate && months.length >= 2 && (
        <>
          <h3>Estimativa por mês</h3>
          <ul className="water-cost-columns">
            {months.map((month) => (
              <li key={month.month}>
                <strong>{currency.format(month.water_cost_cents / 100)}</strong>
                <div className="water-cost-column-track" aria-hidden="true">
                  <div style={{ height: `${(month.water_cost_cents / max) * 100}%` }} />
                </div>
                <span>{monthName.format(new Date(`${month.month}-01T00:00:00Z`))}</span>
                {month.month === estimate.current_month && <small>Até hoje</small>}
              </li>
            ))}
          </ul>
        </>
      )}
      <table className="water-cost-rates">
        <caption>Faixas de consumo</caption>
        <thead>
          <tr>
            <th scope="col">Consumo no mês</th>
            <th scope="col">Cobrança de água</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Até 10.000 L</td>
            <td>R$ 61,77 fixos</td>
          </tr>
          <tr>
            <td>Acima de 10.000 até 20.000 L</td>
            <td>+ R$ 7,09 por 1.000 L nesta faixa</td>
          </tr>
          <tr>
            <td>Acima de 20.000 até 30.000 L</td>
            <td>+ R$ 8,42 por 1.000 L nesta faixa</td>
          </tr>
          <tr>
            <td>Acima de 30.000 até 50.000 L</td>
            <td>+ R$ 11,59 por 1.000 L nesta faixa</td>
          </tr>
          <tr>
            <td>Acima de 50.000 até 90.000 L</td>
            <td>+ R$ 13,74 por 1.000 L nesta faixa</td>
          </tr>
          <tr>
            <td>Acima de 90.000 L</td>
            <td>+ R$ 26,40 por 1.000 L nesta faixa</td>
          </tr>
        </tbody>
      </table>
      <p>
        Exemplo: com 12.000 L no mês, são R$ 61,77 fixos + R$ 14,18 pelos 2.000 L extras. Total
        estimado só de água: R$ 75,95.
      </p>
      <small>Consumo registrado no mês civil.</small>
    </article>
  );
}
