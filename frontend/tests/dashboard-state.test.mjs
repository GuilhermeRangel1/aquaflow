import assert from "node:assert/strict";
import test from "node:test";

import {
  interpolateCurveAtX,
  orderHoursFromMidnight,
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
  assert.equal(resolveDashboardView("training"), "training");
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

test("hourly charts begin at midnight even when the rolling window begins at 15h", () => {
  const source = Array.from({ length: 24 }, (_, index) => ({
    hour: String((15 + index) % 24).padStart(2, "0"),
    volume_liters: index === 3 ? null : index,
  }));
  const ordered = orderHoursFromMidnight(source);
  assert.deepEqual(
    ordered.map((point) => point.hour),
    Array.from({ length: 24 }, (_, index) => String(index).padStart(2, "0")),
  );
  for (const point of source)
    assert.equal(
      ordered.find((item) => item.hour === point.hour),
      point,
    );
  assert.equal(source[0].hour, "15");
});

test("curve interpolation preserves descending recall segments with duplicate x", () => {
  const points = [
    { x: 1, y: 0.15 },
    { x: 1, y: 0.8 },
    { x: 0.9, y: 0.95 },
    { x: 0, y: 1 },
  ];
  assert.ok(Math.abs(interpolateCurveAtX(points, 0.95) - 0.875) < 1e-12);
  assert.equal(interpolateCurveAtX(points, 1), 0.8);
  assert.equal(interpolateCurveAtX([], 0.5), null);
  assert.equal(
    interpolateCurveAtX(
      [
        { x: 0, y: 0 },
        { x: 1, y: 1 },
      ],
      0.5,
    ),
    0.5,
  );
});
