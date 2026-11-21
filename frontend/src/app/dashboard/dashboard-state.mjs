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

/** @param {string | null} requestedView @returns {"overview" | "meters" | "alerts" | "settings"} */
export function resolveDashboardView(requestedView) {
  return requestedView === "meters" || requestedView === "alerts" || requestedView === "settings"
    ? requestedView
    : "overview";
}

/**
 * @param {string | null} requestedView
 * @param {string | null} requestedDeviceId
 * @returns {{ view: "overview" | "meters" | "alerts" | "settings", selectedDeviceId: string | null }}
 */
export function resolveDashboardRoute(requestedView, requestedDeviceId) {
  const view = resolveDashboardView(requestedView);
  return {
    view,
    selectedDeviceId: view === "meters" ? requestedDeviceId : null,
  };
}
