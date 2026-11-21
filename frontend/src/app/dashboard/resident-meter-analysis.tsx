import { useEffect, useState } from "react";

const descriptions = {
  pending: "Em análise",
  normal: "Dentro do padrão",
  possible_anomaly: "Possível alteração",
  insufficient_data: "Sem dados suficientes",
} as const;

type Reading = {
  reading_id: string;
  recorded_at: string;
  flow_rate_liters_minute: number | null;
  status: keyof typeof descriptions;
  alert_id: string | null;
};

export function ResidentMeterAnalysis({
  deviceId,
  timezone,
  load,
  openAlert,
}: {
  deviceId: string;
  timezone: string;
  load: <T>(path: string) => Promise<T>;
  openAlert: (id: string) => Promise<void>;
}) {
  const [readings, setReadings] = useState<Reading[]>();
  const [failed, setFailed] = useState(false);
  const [alertError, setAlertError] = useState("");
  const [openingAlertId, setOpeningAlertId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    async function refresh() {
      try {
        const response = await load<Reading[]>(`devices/${deviceId}/recent-analysis`);
        if (!cancelled) {
          setReadings(response);
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
  }, [deviceId, load]);

  const date = new Intl.DateTimeFormat("pt-BR", {
    timeZone: timezone,
    dateStyle: "short",
    timeStyle: "short",
  });

  async function showAlert(alertId: string) {
    setOpeningAlertId(alertId);
    setAlertError("");
    try {
      await openAlert(alertId);
    } catch {
      setAlertError("Não foi possível abrir o aviso. Tente novamente.");
    } finally {
      setOpeningAlertId(null);
    }
  }

  return (
    <section className="surface chart-card meter-history-card">
      <h2>Últimas leituras</h2>
      {failed && <p role="status">Não foi possível atualizar as leituras.</p>}
      {!failed && !readings && <p role="status">Buscando leituras…</p>}
      {!failed && readings?.length === 0 && <p>As leituras vão aparecer aqui.</p>}
      {!!readings?.length && (
        <table className="resident-readings-table" aria-label="Últimas leituras">
          <thead>
            <tr>
              <th scope="col">Horário</th>
              <th scope="col">Vazão</th>
              <th scope="col">Análise do consumo</th>
            </tr>
          </thead>
          <tbody>
            {readings.map((reading) => (
              <tr key={reading.reading_id}>
                <td>{date.format(new Date(reading.recorded_at))}</td>
                <td>
                  {reading.flow_rate_liters_minute === null
                    ? "Não medida"
                    : `${reading.flow_rate_liters_minute.toLocaleString("pt-BR", { maximumFractionDigits: 3 })} L/min`}
                </td>
                <td>
                  {descriptions[reading.status]}
                  {reading.alert_id && (
                    <button
                      type="button"
                      className="button button--quiet"
                      disabled={openingAlertId !== null}
                      onClick={() => void showAlert(reading.alert_id!)}
                    >
                      {openingAlertId === reading.alert_id ? "Abrindo…" : "Ver aviso"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {alertError && <p role="alert">{alertError}</p>}
    </section>
  );
}
