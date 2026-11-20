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

/** @param {string | null} requestedView @returns {"overview" | "meters" | "alerts" | "settings" | "training"} */
export function resolveDashboardView(requestedView) {
  return requestedView === "meters" ||
    requestedView === "alerts" ||
    requestedView === "settings" ||
    requestedView === "training"
    ? requestedView
    : "overview";
}

/**
 * @param {string | null} requestedView
 * @param {string | null} requestedDeviceId
 * @returns {{ view: "overview" | "meters" | "alerts" | "settings" | "training", selectedDeviceId: string | null }}
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
