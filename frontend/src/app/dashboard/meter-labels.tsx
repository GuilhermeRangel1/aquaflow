import { useEffect, useState, type FormEvent } from "react";

const labels = {
  normal: "Normal",
  anomaly: "Anomalia",
  inconclusive: "Inconclusiva",
  ignored: "Ignorada",
};
type Label = keyof typeof labels;
type Review = {
  id: string;
  label: Label;
  notes: string;
  reviewer_name: string;
  reviewed_at: string;
};
type Page = {
  items: {
    reading: { id: string; recorded_at: string; flow_rate_liters_minute: number | string | null };
    current_label: Review | null;
  }[];
  cursor: string | null;
  has_more: boolean;
};

export function MeterLabels({
  propertyId,
  deviceId,
  load,
}: {
  propertyId: string;
  deviceId: string;
  load: <T>(path: string, init?: RequestInit) => Promise<T>;
}) {
  const path = `properties/${propertyId}/telemetry-labels`;
  const [page, setPage] = useState<Page>();
  const [cursor, setCursor] = useState("");
  const [range, setRange] = useState({ start: "", end: "" });
  const [selected, setSelected] = useState<string[]>([]);
  const [label, setLabel] = useState<Label>("normal");
  const [notes, setNotes] = useState("");
  const [revision, setRevision] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [historyId, setHistoryId] = useState("");
  const [history, setHistory] = useState<Review[]>();
  const [historyError, setHistoryError] = useState(false);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ device_id: deviceId, limit: "25" });
    if (cursor) params.set("cursor", cursor);
    if (range.start) params.set("start", new Date(range.start).toISOString());
    if (range.end) params.set("end", new Date(range.end).toISOString());
    load<Page>(`${path}?${params}`)
      .then((result) => {
        if (active) {
          setPage(result);
          setError("");
        }
      })
      .catch(() => {
        if (active) setError("Não foi possível carregar as leituras.");
      });
    return () => {
      active = false;
    };
  }, [cursor, deviceId, load, path, range, revision]);

  useEffect(() => {
    if (!historyId) return;
    let active = true;
    load<{ items: Review[] }>(`${path}/${historyId}/history`)
      .then((result) => {
        if (active) setHistory(result.items);
      })
      .catch(() => {
        if (active) setHistoryError(true);
      });
    return () => {
      active = false;
    };
  }, [historyId, load, path, revision]);

  function changePage(next: string) {
    setPage(undefined);
    setSelected([]);
    setError("");
    setHistoryId("");
    setCursor(next);
    setRevision((value) => value + 1);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving || !selected.length || notes.trim().length < 3) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await load(path, {
        method: "POST",
        body: JSON.stringify({ device_id: deviceId, reading_ids: selected, label, notes }),
      });
      setNotes("");
      setNotice("Revisão registrada.");
      changePage(cursor);
    } catch {
      setError("Não foi possível registrar a revisão. Confira os dados e tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="surface settings-card telemetry-review">
      <h2>Revisar leituras</h2>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const fields = new FormData(event.currentTarget);
          const start = String(fields.get("start") ?? "");
          const end = String(fields.get("end") ?? "");
          if (start && end && start >= end) {
            setError("O fim deve ser posterior ao início.");
            return;
          }
          setRange({ start, end });
          changePage("");
        }}
      >
        <div className="settings-grid">
          <label className="field">
            Início (hora local)
            <input type="datetime-local" name="start" />
          </label>
          <label className="field">
            Fim (hora local)
            <input type="datetime-local" name="end" />
          </label>
        </div>
        <button type="submit" className="button button--quiet" disabled={saving}>
          Filtrar
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!page && !error && <p role="status">Carregando leituras…</p>}
      {!page && error && <button onClick={() => changePage(cursor)}>Tentar novamente</button>}
      {page?.items.length === 0 && <p>Nenhuma leitura no período.</p>}
      {!!page?.items.length && (
        <form onSubmit={(event) => void save(event)}>
          <fieldset disabled={saving}>
            <legend>Selecione as leituras</legend>
            {page.items.map(({ reading, current_label }) => (
              <div key={reading.id} className="telemetry-review-row">
                <label>
                  <input
                    type="checkbox"
                    checked={selected.includes(reading.id)}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setSelected((ids) =>
                        checked ? [...ids, reading.id] : ids.filter((id) => id !== reading.id),
                      );
                    }}
                  />{" "}
                  {new Date(reading.recorded_at).toLocaleString("pt-BR")} ·{" "}
                  {reading.flow_rate_liters_minute === null
                    ? "Vazão indisponível"
                    : `${Number(reading.flow_rate_liters_minute).toLocaleString("pt-BR")} L/min`}{" "}
                  <span>{current_label ? labels[current_label.label] : "Sem rótulo"}</span>
                </label>{" "}
                <button
                  type="button"
                  className="button button--quiet"
                  onClick={() => {
                    setHistory(undefined);
                    setHistoryError(false);
                    setHistoryId((id) => (id === reading.id ? "" : reading.id));
                  }}
                >
                  Histórico
                </button>
                {historyId === reading.id &&
                  (historyError ? (
                    <p role="alert">Não foi possível carregar o histórico.</p>
                  ) : !history ? (
                    <p role="status">Carregando histórico…</p>
                  ) : !history.length ? (
                    <p>Sem revisões.</p>
                  ) : (
                    <ul>
                      {history.map((review) => (
                        <li key={review.id}>
                          {labels[review.label]} · {review.reviewer_name} ·{" "}
                          {new Date(review.reviewed_at).toLocaleString("pt-BR")} · {review.notes}
                        </li>
                      ))}
                    </ul>
                  ))}
              </div>
            ))}
            <label className="field">
              Rótulo
              <select value={label} onChange={(event) => setLabel(event.target.value as Label)}>
                {Object.entries(labels).map(([value, name]) => (
                  <option key={value} value={value}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Justificativa
              <textarea
                required
                minLength={3}
                maxLength={1000}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>
            <button
              type="submit"
              className="button button--primary"
              disabled={!selected.length || notes.trim().length < 3}
            >
              Registrar revisão ({selected.length})
            </button>
          </fieldset>
        </form>
      )}
      {cursor && (
        <button
          type="button"
          disabled={saving}
          className="button button--quiet"
          onClick={() => changePage("")}
        >
          Voltar ao início
        </button>
      )}
      {page?.has_more && page.cursor && (
        <button
          type="button"
          disabled={saving}
          className="button button--quiet"
          onClick={() => changePage(page.cursor ?? "")}
        >
          Mais leituras
        </button>
      )}
    </section>
  );
}
