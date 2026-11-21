import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveActivePropertyId,
  resolveDashboardRoute,
  resolveDashboardView,
} from "../src/app/dashboard/dashboard-state.mjs";

test("selects the first property when the dashboard opens without a prior selection", () => {
  assert.equal(resolveActivePropertyId(undefined, "", ["property-1", "property-2"]), "property-1");
});

test("only exposes supported dashboard destinations", () => {
  assert.equal(resolveDashboardView("meters"), "meters");
  assert.equal(resolveDashboardView("alerts"), "alerts");
  assert.equal(resolveDashboardView("unknown"), "overview");
});

test("opens a meter detail only inside the meters view", () => {
  assert.deepEqual(resolveDashboardRoute("meters", "device-123"), {
    view: "meters",
    selectedDeviceId: "device-123",
  });
  assert.deepEqual(resolveDashboardRoute("overview", "device-123"), {
    view: "overview",
    selectedDeviceId: null,
  });
});
