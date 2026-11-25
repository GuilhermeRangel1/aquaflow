/**
 * @param {string | undefined} requestedPropertyId
 * @param {string} selectedPropertyId
 * @param {string[]} availablePropertyIds
 * @returns {string}
 */
export function resolveActivePropertyId(
  requestedPropertyId,
  selectedPropertyId,
  availablePropertyIds,
) {
  if (requestedPropertyId) return requestedPropertyId;
  if (availablePropertyIds.includes(selectedPropertyId)) return selectedPropertyId;
  return availablePropertyIds[0] ?? "";
}

/** @param {string | null} requestedView @returns {"overview" | "meters" | "alerts" | "settings" | "training" | "telemetry"} */
export function resolveDashboardView(requestedView) {
  return requestedView === "meters" ||
    requestedView === "alerts" ||
    requestedView === "settings" ||
    requestedView === "training" ||
    requestedView === "telemetry"
    ? requestedView
    : "overview";
}

/**
 * @param {string | null} requestedView
 * @param {string | null} requestedDeviceId
 * @returns {{ view: "overview" | "meters" | "alerts" | "settings" | "training" | "telemetry", selectedDeviceId: string | null }}
 */
export function resolveDashboardRoute(requestedView, requestedDeviceId) {
  const view = resolveDashboardView(requestedView);
  return {
    view,
    selectedDeviceId: view === "meters" ? requestedDeviceId : null,
  };
}
/**
 * Present the rolling 24-hour window in local clock order, preserving each value.
 * @template {{ hour: string }} T
 * @param {T[]} points
 * @returns {T[]}
 */
export function orderHoursFromMidnight(points) {
  return [...points].sort((left, right) => Number(left.hour) - Number(right.hour));
}
/**
 * Interpolate along the original segments, preserving vertical/duplicate-x points.
 * @param {{x:number,y:number}[]} points
 * @param {number} x
 * @returns {number | null}
 */
export function interpolateCurveAtX(points, x) {
  for (let index = 1; index < points.length; index++) {
    const low = points[index - 1];
    const high = points[index];
    if (x < Math.min(low.x, high.x) || x > Math.max(low.x, high.x)) continue;
    if (low.x === high.x) return Math.max(low.y, high.y);
    return low.y + ((high.y - low.y) * (x - low.x)) / (high.x - low.x);
  }
  return points.find((point) => point.x === x)?.y ?? null;
}

const ANALYSIS_WINDOW_MS = 5 * 60_000;

/**
 * High-frequency meters are analyzed in five-minute windows aligned to the clock.
 * @param {number} now
 * @returns {number}
 */
export function nextAnalysisAt(now) {
  return (Math.floor(now / ANALYSIS_WINDOW_MS) + 1) * ANALYSIS_WINDOW_MS;
}

/**
 * @param {{ reading_id: string, status: string, predicted_anomaly: boolean | null, anomaly_probability: number | null }[] | null} analyses
 * @param {string} readingId
 * @param {boolean} grouped
 * @returns {string}
 */
export function describeReadingAnalysis(analyses, readingId, grouped) {
  if (!analyses) return "Consulta indisponível";
  const result = analyses.find((analysis) => analysis.reading_id === readingId);
  if (!result) return grouped ? "Sem análise própria" : "Ainda sem resultado";
  if (result.status === "skipped" || result.predicted_anomaly === null)
    return "Sem dados suficientes";
  const label = result.predicted_anomaly ? "Possível anomalia" : "Normal";
  if (result.anomaly_probability === null) return label;
  const chance = result.anomaly_probability.toLocaleString("pt-BR", {
    style: "percent",
    maximumFractionDigits: 1,
  });
  return `${label} · ${chance} de chance de anomalia`;
}

/**
 * @param {string} reason
 * @returns {string}
 */
export function explainSkippedAnalysis(reason) {
  if (reason.startsWith("Cobertura insuficiente"))
    return "Ainda não havia leituras suficientes para cobrir os 5 minutos.";
  if (reason.startsWith("Lacuna"))
    return "Faltaram leituras no meio do período. Confira a energia e o Wi-Fi do medidor.";
  if (reason.startsWith("O contador de volume diminuiu"))
    return "O contador do medidor voltou atrás, como acontece quando ele reinicia.";
  if (reason.startsWith("Fuso"))
    return "O fuso horário desta casa é diferente do usado para ensinar o sistema.";
  return "As leituras disponíveis não foram suficientes para uma conclusão.";
}

/**
 * Results come ordered by processing time; the latest one follows the reading time.
 * @template {{ recorded_at: string }} T
 * @param {T[] | null} analyses
 * @returns {T | undefined}
 */
export function newestAnalysis(analyses) {
  return analyses?.reduce(
    (newest, item) =>
      Date.parse(item.recorded_at) > Date.parse(newest.recorded_at) ? item : newest,
    analyses[0],
  );
}
