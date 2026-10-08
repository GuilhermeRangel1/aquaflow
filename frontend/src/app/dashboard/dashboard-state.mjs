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

/** @param {string | null} requestedView */
export function resolveDashboardView(requestedView) {
  return requestedView === "meters" || requestedView === "alerts" || requestedView === "settings" ? requestedView : "overview";
}
