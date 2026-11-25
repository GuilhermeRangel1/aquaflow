import { useEffect, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { describeReadingAnalysis, newestAnalysis, nextAnalysisAt } from "./dashboard-state.mjs";
import { MeterInference } from "./meter-inference";
import { SystemStatusCard } from "./system-status-card";

type Reading = {
  id: string;
  event_id: string;
  recorded_at: string;
  received_at: string;
  flow_rate_liters_minute: string | number | null;
  cumulative_volume_liters: string | number | null;
  quality: string;
  battery_percent: number | null;
  signal_dbm: number | null;
  firmware_version: string | null;
};
type Health = { connectivity: "online" | "offline" | "never_connected" };
type Analysis = {
  reading_id: string;
  recorded_at: string;
  status: "scored" | "skipped";
  predicted_anomaly: boolean | null;
  anomaly_probability: number | null;
};
type ReadingPage = {
  items: Reading[];
  cursor: string | null;
  has_more: boolean;
  queried_at: string;
};

export function TelemetryView({
  devices,
  propertyId,
  timezone,
  load,
}: {
  devices: {
    id: string;
    name: string;
    serial_number?: string;
    expected_interval_seconds: number;
  }[];
  propertyId: string;
  timezone: string;
  load: <T>(path: string, init?: RequestInit) => Promise<T>;
}) {
  const [selection, setSelection] = useState("");
  const deviceId = devices.find((device) => device.id === selection)?.id ?? devices[0]?.id;
  const device = devices.find((item) => item.id === deviceId);
  const deviceName = device
    ? [device.name, device.serial_number].filter(Boolean).join(" · ")
    : "Nenhum medidor cadastrado";
  const [open, setOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !pickerRef.current?.contains(event.target))
        setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <div className="telemetry-layout">
      <div className="surface telemetry-picker" ref={pickerRef}>
        <span>Medidor acompanhado</span>
        <button
          ref={triggerRef}
          type="button"
          className="telemetry-picker-trigger shell-property-picker__trigger"
          aria-label={`Alterar medidor acompanhado: ${deviceName}`}
          aria-expanded={open}
          disabled={!deviceId}
          onClick={() => setOpen(!open)}
        >
          <span className="shell-property-picker__current">{deviceName}</span>
          <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="m5.5 7.5 4.5 4.5 4.5-4.5" />
          </svg>
        </button>
        {open && (
          <div className="shell-property-picker__menu" role="group" aria-label="Medidores">
            {devices.map((device) => (
              <button
                key={device.id}
                type="button"
                aria-pressed={device.id === deviceId}
                className={`shell-property-picker__option${device.id === deviceId ? " shell-property-picker__option--selected" : ""}`}
                onClick={() => {
                  setSelection(device.id);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
              >
                <span className="shell-property-picker__option-copy">
                  <span>{device.name}</span>
                  {device.serial_number && <small>{device.serial_number}</small>}
                </span>
                {device.id === deviceId && (
                  <span className="shell-property-picker__check" aria-hidden="true">
                    ✓
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
      {deviceId && (
        <LiveReadings
          key={deviceId}
          deviceId={deviceId}
          propertyId={propertyId}
          timezone={timezone}
          interval={
            devices.find((device) => device.id === deviceId)?.expected_interval_seconds ?? 30
          }
          load={load}
        />
      )}
    </div>
  );
}

function LiveReadings({
  deviceId,
  propertyId,
  timezone,
  interval,
  load,
}: {
  deviceId: string;
  propertyId: string;
  timezone: string;
  interval: number;
  load: <T>(path: string, init?: RequestInit) => Promise<T>;
}) {
  const [page, setPage] = useState<ReadingPage>();
  const [older, setOlder] = useState<ReadingPage[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [minutes, setMinutes] = useState(15);
  const [series, setSeries] = useState<Reading[]>([]);
  const [expanded, setExpanded] = useState<string[]>([]);
  const date = (value: string | number) =>
    new Date(value).toLocaleString("pt-BR", { timeZone: timezone });
  const [analyses, setAnalyses] = useState<Analysis[] | null>(null);
  const [olderAnalyses, setOlderAnalyses] = useState<Partial<Record<string, Analysis[]>>>({});
  const [health, setHealth] = useState<Health>();
  const [paused, setPaused] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<number>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (paused) return;
    let active = true;
    let timer: number | undefined;
    async function update() {
      try {
        const [page, status] = await Promise.all([
          load<ReadingPage>(`devices/${deviceId}/readings?limit=4`),
          load<Health>(`devices/${deviceId}/health`),
        ]);
        const params = new URLSearchParams({ device_id: deviceId, limit: "100" });
        // Results arrive by processing time, so old readings reprocessed after a restart
        // must not hide the newest ones.
        if (page.items[0]) {
          params.set(
            "start",
            new Date(Date.parse(page.items[0].recorded_at) - 6 * 3_600_000).toISOString(),
          );
        }
        const analysis = await load<{ items: Analysis[] }>(
          `properties/${propertyId}/ml-inferences?${params}`,
        ).catch(() => null);
        if (active) {
          setUpdatedAt(Date.now());
          setPage(page);
          setAnalyses(analysis?.items ?? null);
          setHealth(status);
          setFailed(false);
        }
      } catch {
        if (active) setFailed(true);
      } finally {
        if (active && !paused) timer = window.setTimeout(update, 5000);
      }
    }
    void update();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [deviceId, load, paused, refresh, propertyId]);

  const chartCache = useRef<{
    deviceId: string;
    minutes: number;
    refresh: number;
    fetchedAt: number;
    samples: Reading[];
  } | null>(null);
  const [chartFailed, setChartFailed] = useState(false);
  useEffect(() => {
    if (paused) return;
    let active = true;
    let timer: number | undefined;
    async function updateChart() {
      const cached = chartCache.current;
      const previous =
        cached?.deviceId === deviceId && cached.minutes === minutes && cached.refresh === refresh
          ? cached
          : null;
      const params = new URLSearchParams({ window_minutes: String(minutes), limit: "500" });
      if (previous) {
        // Revisit recent arrivals so retries and late commits do not leave gaps.
        params.set("received_since", new Date(previous.fetchedAt - 60_000).toISOString());
      }
      try {
        const samples = new Map((previous?.samples ?? []).map((reading) => [reading.id, reading]));
        let queriedAt: number | undefined;
        while (active) {
          const chunk = await load<ReadingPage>(`devices/${deviceId}/readings?${params}`);
          if (queriedAt === undefined) {
            queriedAt = Date.parse(chunk.queried_at);
            params.set("start", new Date(queriedAt - minutes * 60_000).toISOString());
            params.delete("window_minutes");
          }
          for (const reading of chunk.items) samples.set(reading.id, reading);
          if (!chunk.has_more || !chunk.cursor) break;
          params.set("cursor", chunk.cursor);
        }
        if (active && queriedAt !== undefined) {
          const serverTime = queriedAt;
          const start = serverTime - minutes * 60_000;
          const merged = [...samples.values()].filter(
            (reading) => Date.parse(reading.recorded_at) >= start,
          );
          chartCache.current = {
            deviceId,
            minutes,
            refresh,
            fetchedAt: serverTime,
            samples: merged,
          };
          setSeries(merged.filter((reading) => Date.parse(reading.recorded_at) < serverTime));
          setChartFailed(false);
        }
      } catch {
        if (active) setChartFailed(true);
      } finally {
        if (active) timer = window.setTimeout(updateChart, 5000);
      }
    }
    void updateChart();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [deviceId, load, minutes, paused, refresh]);

  const grouped = interval < 300;
  const nextAnalysis =
    grouped && health?.connectivity === "online" && updatedAt !== undefined
      ? nextAnalysisAt(updatedAt)
      : null;
  const history = older.at(-1) ?? page;
  const latest = page?.items[0];
  const latestAnalysisId = newestAnalysis(analyses)?.reading_id ?? latest?.id;
  const readings =
    page &&
    Array.from(
      new Map(
        [page, ...older].flatMap((result) => result.items).map((reading) => [reading.id, reading]),
      ).values(),
    ).sort((a, b) => Date.parse(b.recorded_at) - Date.parse(a.recorded_at));
  const chart: { time: number; flow: number | null }[] = [];
  for (const reading of [...series].sort(
    (a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at),
  )) {
    const time = Date.parse(reading.recorded_at);
    const previous = chart.at(-1);
    if (previous && time - previous.time > interval * 1500) {
      chart.push({ time: previous.time + interval * 1000, flow: null });
    }
    chart.push({
      time,
      flow:
        reading.quality === "valid" && reading.flow_rate_liters_minute !== null
          ? Number(reading.flow_rate_liters_minute)
          : null,
    });
  }

  async function loadOlder() {
    if (loadingOlder || !history?.has_more || !history.cursor) return;
    setLoadingOlder(true);
    setHistoryError(false);
    try {
      const query = new URLSearchParams({ limit: "10", cursor: history.cursor });
      const result = await load<ReadingPage>(`devices/${deviceId}/readings?${query}`);
      if (result.items.length) {
        const params = new URLSearchParams({ device_id: deviceId, limit: "100" });
        for (const reading of result.items) params.append("latest_for_reading_ids", reading.id);
        const response = await load<{ items: Analysis[] }>(
          `properties/${propertyId}/ml-inferences?${params}`,
        );
        const byReading = new Map(
          response.items.map((analysis) => [analysis.reading_id, analysis]),
        );
        setOlderAnalyses((previous) => ({
          ...previous,
          ...Object.fromEntries(
            result.items.map((reading) => {
              const analysis = byReading.get(reading.id);
              return [reading.id, analysis ? [analysis] : []];
            }),
          ),
        }));
      }
      setOlder((previous) => [...previous, result]);
    } catch {
      setHistoryError(true);
    } finally {
      setLoadingOlder(false);
    }
  }
  return (
    <>
      <section className="surface telemetry-status">
        <strong>
          {health
            ? {
                online: "Recebendo leituras",
                offline: "Sem comunicação",
                never_connected: "Aguardando primeira leitura",
              }[health.connectivity]
            : failed
              ? "Consulta indisponível"
              : "Consultando conexão…"}
        </strong>
        {latest && <small>Último recebimento · {date(latest.received_at)}</small>}
      </section>
      <section className="telemetry-latest">
        <small>Última leitura{latest && ` · ${date(latest.recorded_at)}`}</small>
        <div className="telemetry-values">
          <div>
            <strong>
              {formatMeasure(
                latest?.quality === "valid" ? latest.flow_rate_liters_minute : null,
                "L/min",
              )}
            </strong>
            <small>Vazão registrada</small>
          </div>
          <div>
            <strong>{formatMeasure(latest?.cumulative_volume_liters, "L")}</strong>
            <small>Volume acumulado do medidor</small>
          </div>
        </div>
      </section>
      <section className="surface telemetry-card">
        <header className="telemetry-toolbar">
          <div>
            <h2>Vazão ao vivo</h2>
            <small>Litros por minuto</small>
          </div>
          <div className="telemetry-period" role="group" aria-label="Período do gráfico">
            {(
              [
                [15, "15 minutos"],
                [60, "1 hora"],
                [360, "6 horas"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={minutes === value}
                disabled={paused}
                onClick={() => setMinutes(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </header>
        {chartFailed && <p role="alert">Não foi possível atualizar o gráfico de vazão.</p>}
        {failed && <p role="alert">Não foi possível consultar o medidor.</p>}
        {!readings && !failed && <p role="status">Consultando leituras…</p>}
        {readings?.length === 0 && <p>Nenhuma leitura registrada.</p>}
        {chart.some((point) => point.flow !== null) ? (
          <div role="group" aria-label="Gráfico de vazão das últimas leituras em litros por minuto">
            <ResponsiveContainer width="100%" height={230}>
              <LineChart data={chart} margin={{ top: 16, right: 12, bottom: 8, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--surface-soft)" />
                <XAxis
                  axisLine={false}
                  tickLine={false}
                  dataKey="time"
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  tickFormatter={(value: number) =>
                    new Date(value).toLocaleTimeString("pt-BR", {
                      hour: "2-digit",
                      minute: "2-digit",
                      timeZone: timezone,
                    })
                  }
                />
                <YAxis axisLine={false} tickLine={false} width={44} />
                <Tooltip labelFormatter={(value) => date(Number(value))} />
                <Line
                  type="stepAfter"
                  dot={chart.length === 1}
                  strokeWidth={2}
                  dataKey="flow"
                  name="Vazão (L/min)"
                  stroke="var(--accent, #087b83)"
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : readings?.length ? (
          <p className="telemetry-empty">Sem vazão válida neste período.</p>
        ) : null}
      </section>
      <div className="telemetry-toolbar telemetry-controls">
        <small>{updatedAt ? `Atualizado às ${date(updatedAt)} · ${timezone}` : timezone}</small>
        <div>
          <button type="button" className="button button--quiet" onClick={() => setPaused(!paused)}>
            {paused ? "Retomar atualização" : "Pausar atualização"}
          </button>
          <button
            type="button"
            className="button button--quiet"
            disabled={paused}
            onClick={() => setRefresh(refresh + 1)}
          >
            Atualizar agora
          </button>
        </div>
      </div>
      <section className="surface telemetry-card">
        <h2>Como funciona a análise</h2>
        <p>
          O sistema compara a água que passou com exemplos de consumo comum e fora do comum.{" "}
          {grouped
            ? "Neste medidor, as leituras são analisadas juntas, em períodos de 5 minutos. A vazão aparece na hora, mas o resultado só sai quando o período termina."
            : "Neste medidor, cada leitura é comparada com a anterior."}
        </p>
        {nextAnalysis !== null && (
          <p>
            Próximo resultado a partir de{" "}
            <strong>
              {new Date(nextAnalysis).toLocaleTimeString("pt-BR", {
                hour: "2-digit",
                minute: "2-digit",
                timeZone: timezone,
              })}
            </strong>
            , se não faltarem leituras.
          </p>
        )}
        <dl className="telemetry-attribute-grid">
          <div>
            <dt>Normal</dt>
            <dd>O uso ficou parecido com o consumo comum.</dd>
          </div>
          <div>
            <dt>Possível anomalia</dt>
            <dd>O uso ficou fora do comum. Vale verificar, mas não confirma vazamento.</dd>
          </div>
          <div>
            <dt>Sem dados suficientes</dt>
            <dd>Faltaram leituras para analisar. Não quer dizer que está normal.</dd>
          </div>
        </dl>
        <small>
          Um aviso é criado quando dois resultados seguidos indicam possível anomalia, para evitar
          alarme por um uso isolado.
        </small>
      </section>
      {latestAnalysisId && (
        <MeterInference
          key={latestAnalysisId}
          readingId={latestAnalysisId}
          deviceId={deviceId}
          propertyId={propertyId}
          load={load}
          paused={paused}
          variant="summary"
          timezone={timezone}
        />
      )}
      <section className="surface telemetry-card">
        <h2>Leituras e análises recentes</h2>
        <div className="telemetry-row telemetry-table-heading">
          <span>Horário da leitura</span>
          <span>Vazão</span>
          <span>Análise</span>
          <span>Detalhes</span>
        </div>
        {readings?.map((reading) => (
          <details
            key={reading.id}
            className="telemetry-history-entry"
            onToggle={(event) => {
              const opened = event.currentTarget.open;
              setExpanded((ids) =>
                opened
                  ? [...ids.filter((id) => id !== reading.id), reading.id]
                  : ids.filter((id) => id !== reading.id),
              );
            }}
          >
            <summary className="telemetry-row">
              <span>{date(reading.recorded_at)}</span>
              <span>{formatMeasure(reading.flow_rate_liters_minute, "L/min")}</span>
              <span>
                {describeReadingAnalysis(
                  olderAnalyses[reading.id] ?? analyses,
                  reading.id,
                  grouped,
                )}
              </span>
              <span className="telemetry-disclosure-action">
                <span>Ver detalhes</span>
                <span>Recolher</span>
              </span>
            </summary>
            <div className="telemetry-reading-detail">
              <header>
                <h3>Detalhes da leitura</h3>
                <p>{date(reading.recorded_at)}</p>
              </header>
              <dl className="telemetry-attribute-grid telemetry-reading-fields">
                <div>
                  <dt>Medição</dt>
                  <dd>{date(reading.recorded_at)}</dd>
                </div>
                <div>
                  <dt>Recebimento</dt>
                  <dd>{date(reading.received_at)}</dd>
                </div>
                <div>
                  <dt>Situação da leitura</dt>
                  <dd>{describeQuality(reading.quality)}</dd>
                </div>
                <div>
                  <dt>Vazão registrada</dt>
                  <dd>{formatMeasure(reading.flow_rate_liters_minute, "L/min")}</dd>
                </div>
                <div>
                  <dt>Volume acumulado</dt>
                  <dd>{formatMeasure(reading.cumulative_volume_liters, "L")}</dd>
                </div>
                <div>
                  <dt>Bateria / Sinal</dt>
                  <dd>
                    {reading.battery_percent == null
                      ? "Não informada"
                      : formatMeasure(reading.battery_percent, "%")}{" "}
                    /{" "}
                    {reading.signal_dbm == null
                      ? "Não informado"
                      : formatMeasure(reading.signal_dbm, "dBm")}
                  </dd>
                </div>
              </dl>
              {expanded.includes(reading.id) && (
                <div>
                  <MeterInference
                    readingId={reading.id}
                    deviceId={deviceId}
                    propertyId={propertyId}
                    load={load}
                    paused={paused}
                    timezone={timezone}
                    variant="history"
                  />
                </div>
              )}
              <details className="telemetry-analysis-details">
                <summary>Identificação técnica da leitura</summary>
                <dl className="telemetry-attribute-grid">
                  <div>
                    <dt>Evento</dt>
                    <dd>{reading.event_id}</dd>
                  </div>
                  <div>
                    <dt>Programa da placa</dt>
                    <dd>{reading.firmware_version ?? "Não informado"}</dd>
                  </div>
                </dl>
              </details>
            </div>
          </details>
        ))}
        <div className="telemetry-history-footer">
          <small>{readings?.length ?? 0} leituras · Resultados disponíveis nesta consulta</small>
          {historyError && <p role="alert">Não foi possível carregar leituras anteriores.</p>}
          {history?.has_more && (
            <button
              type="button"
              className="button telemetry-load-more"
              disabled={loadingOlder}
              onClick={() => void loadOlder()}
            >
              {loadingOlder ? "Carregando…" : "Carregar mais leituras"}
              {!loadingOlder && <span aria-hidden="true">↓</span>}
            </button>
          )}
        </div>
      </section>
      <SystemStatusCard propertyId={propertyId} timezone={timezone} paused={paused} load={load} />
    </>
  );
}

function formatMeasure(value: string | number | null | undefined, unit: string) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return `${Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 3 })} ${unit}`;
}

function describeQuality(quality: string) {
  return (
    {
      valid: "Válida",
      counter_reset: "Contador do medidor reiniciado",
      out_of_order: "Chegou fora de ordem",
    }[quality] ?? "Não pôde ser usada"
  );
}
