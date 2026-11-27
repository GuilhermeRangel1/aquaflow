import assert from "node:assert/strict";
import test from "node:test";

import {
  describeReadingAnalysis,
  explainSkippedAnalysis,
  interpolateCurveAtX,
  newestAnalysis,
  describeElapsed,
  nextAnalysisAt,
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

test("the next analysis is the end of the current five-minute window", () => {
  const at = (value) => Date.parse(value);
  assert.equal(nextAnalysisAt(at("2026-11-25T12:03:45Z")), at("2026-11-25T12:05:00Z"));
  assert.equal(nextAnalysisAt(at("2026-11-25T12:05:00Z")), at("2026-11-25T12:10:00Z"));
});

test("analysis results use plain language and never turn missing data into normal", () => {
  const scored = (predicted_anomaly) => [
    { reading_id: "a", status: "scored", predicted_anomaly, anomaly_probability: 0.505 },
  ];
  assert.match(describeReadingAnalysis(scored(true), "a", true), /^Possível anomalia · 50,5/);
  assert.match(describeReadingAnalysis(scored(false), "a", true), /^Normal · 50,5/);
  const skipped = [
    { reading_id: "a", status: "skipped", predicted_anomaly: null, anomaly_probability: null },
  ];
  assert.equal(describeReadingAnalysis(skipped, "a", true), "Sem dados suficientes");
  assert.equal(describeReadingAnalysis([], "a", true), "Sem análise própria");
  assert.equal(describeReadingAnalysis([], "a", false), "Ainda sem resultado");
  assert.equal(describeReadingAnalysis(null, "a", true), "Consulta indisponível");
});

test("skipped analyses explain the reason in plain language", () => {
  assert.match(
    explainSkippedAnalysis("Lacuna ou timestamp duplicado na janela de cinco minutos."),
    /Wi-Fi/,
  );
  assert.match(explainSkippedAnalysis("motivo novo"), /não foram suficientes/);
});

test("the latest analysis follows the reading time, not the processing order", () => {
  const older = { reading_id: "old", recorded_at: "2026-11-25T12:00:00Z" };
  const newer = { reading_id: "new", recorded_at: "2026-11-25T12:05:00Z" };
  assert.equal(newestAnalysis([older, newer]).reading_id, "new");
  assert.equal(newestAnalysis([]), undefined);
  assert.equal(newestAnalysis(null), undefined);
});

test("elapsed time is written in plain words", () => {
  assert.equal(describeElapsed(20_000), "menos de 1 minuto");
  assert.equal(describeElapsed(60_000), "1 minuto");
  assert.equal(describeElapsed(52 * 60_000), "52 minutos");
  assert.equal(describeElapsed(60 * 60_000), "1 hora");
  assert.equal(describeElapsed(185 * 60_000), "3 horas e 5 minutos");
  assert.equal(describeElapsed(26 * 3_600_000), "1 dia");
  assert.equal(describeElapsed(-5), "menos de 1 minuto");
});
