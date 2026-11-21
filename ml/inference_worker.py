"""Persist experimental predictions for newly received telemetry."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

import joblib
import numpy as np
from feature_transforms import FEATURE_NAMES, transform_reading
from feature_transforms import transform_window

logger = logging.getLogger("aquaflow.ml.inference")
MODEL_WINDOW_SECONDS = 300
_health_lock = Lock()
_health: dict[str, Any] = {
    "status": "starting",
    "model_name": None,
    "model_version": None,
    "started_at": None,
    "last_check_at": None,
    "processed_records": 0,
    "failed_batches": 0,
}


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        with _health_lock:
            body = json.dumps(_health).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _start_health_server() -> None:
    port = int(os.getenv("ML_HEALTH_PORT", "8081"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    Thread(target=server.serve_forever, daemon=True).start()


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


async def _record_ml_alert(
    connection: Any,
    *,
    inference_id: Any,
    reading: Any,
    model_version: str,
    probability: float,
    threshold: float,
    features: dict[str, Any],
    explanation: dict[str, Any],
    reason: str,
) -> None:
    """Create or update one actionable alert for consecutive model positives."""
    end = reading["recorded_at"]
    # Serialize decisions for a meter, including reprocessing by another worker.
    active = await connection.fetchval(
        "SELECT is_active FROM devices WHERE id = $1 FOR NO KEY UPDATE", reading["device_id"]
    )
    if not active:
        return
    already_scored = await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM ml_inferences WHERE reading_id = $1 AND id <> $2)",
        reading["id"], inference_id,
    )
    if already_scored:
        return
    previous = await connection.fetchrow(
        """
        SELECT i.id, i.predicted_anomaly, r.recorded_at,
               i.feature_values->>'elapsed_minutes' AS minutes
        FROM ml_inferences i JOIN telemetry_readings r ON r.id = i.reading_id
        WHERE r.device_id = $1 AND i.model_version = $2
          AND r.recorded_at < $3
          AND r.recorded_at >= $3 - $4::double precision * interval '1 second'
        ORDER BY r.recorded_at DESC, r.id DESC LIMIT 1
        """,
        reading["device_id"], model_version, end,
        float(features["elapsed_minutes"]) * 60 + 1,
    )
    if previous is None or previous["predicted_anomaly"] is not True:
        return
    previous_end = previous["recorded_at"]
    start = previous_end - timedelta(minutes=float(previous["minutes"]))
    existing = await connection.fetchrow(
        """
        SELECT a.id AS alert_id, a.status, e.id AS anomaly_id, e.evidence, e.window_end
        FROM alerts AS a
        JOIN anomaly_events AS e ON e.id = a.anomaly_id
        WHERE e.device_id = $1
          AND e.detector_type = 'ml_anomaly'
          AND e.evidence->>'episode_policy' = 'consecutive-v1'
          AND e.window_end >= $2 AND e.window_start < $3
        ORDER BY (e.window_end >= $3) DESC, e.window_end DESC, a.id DESC
        LIMIT 1
        FOR UPDATE OF a, e
        """,
        reading["device_id"], previous_end, end,
    )
    now = datetime.now(UTC)
    signal_values = {
        "flow_rate_liters_minute": features["flow_rate_liters_minute"],
        "volume_delta_liters": features["volume_delta_liters"],
        "elapsed_minutes": features["elapsed_minutes"],
        "input_derivation": explanation.get("input_derivation"),
        "top_signals": explanation.get("top_signals", []),
    }
    if existing is not None:
        if existing["window_end"] >= end or existing["status"] not in ("open", "acknowledged"):
            return
        evidence = _json_object(existing["evidence"])
        inference_ids = list(evidence.get("ml_inference_ids", []))
        inference_key = str(inference_id)
        if inference_key in inference_ids:
            return
        inference_ids.append(inference_key)
        evidence.update(
            {
                "ml_inference_ids": inference_ids,
                "latest_ml_inference_id": inference_key,
                "latest_reading_id": str(reading["id"]),
                "model_version": model_version,
                "anomaly_probability": probability,
                "maximum_anomaly_probability": max(
                    float(evidence.get("maximum_anomaly_probability", 0)), probability
                ),
                "classification_threshold": threshold,
                "latest_signals": signal_values,
                "occurrence_count": len(inference_ids),
            }
        )
        await connection.execute(
            """
            UPDATE anomaly_events
            SET score = GREATEST(score, $2), reason = $3, window_end = $4,
                evidence = $5::json
            WHERE id = $1
            """,
            existing["anomaly_id"],
            Decimal(str(probability)),
            reason,
            reading["recorded_at"],
            json.dumps(evidence, allow_nan=False),
        )
        return

    inference_key = str(inference_id)
    evidence = {
        "episode_policy": "consecutive-v1",
        "ml_inference_ids": [str(previous["id"]), inference_key],
        "latest_ml_inference_id": inference_key,
        "reading_id": str(reading["id"]),
        "latest_reading_id": str(reading["id"]),
        "model_version": model_version,
        "anomaly_probability": probability,
        "maximum_anomaly_probability": probability,
        "classification_threshold": threshold,
        "latest_signals": signal_values,
        "occurrence_count": 2,
    }
    anomaly_id = uuid4()
    alert_id = uuid4()
    await connection.execute(
        """
        INSERT INTO anomaly_events (
            id, property_id, device_id, detector_type, score, severity, reason,
            window_start, window_end, evidence, detected_at
        ) VALUES ($1, $2, $3, 'ml_anomaly', $4, 'medium', $5, $6, $7, $8::json, $9)
        """,
        anomaly_id,
        reading["property_id"],
        reading["device_id"],
        Decimal(str(probability)),
        reason,
        start,
        end,
        json.dumps(evidence, allow_nan=False),
        now,
    )
    await connection.execute(
        """
        INSERT INTO alerts (id, anomaly_id, status, channel, created_at)
        VALUES ($1, $2, 'open', 'dashboard', $3)
        """,
        alert_id,
        anomaly_id,
        now,
    )



def load_model(model_path: Path, report_path: Path) -> tuple[Any, dict[str, Any], str]:
    """Load only a model whose local training report records its matching hash."""
    pointer_path = model_path.parent / "active-model.json"
    if pointer_path.is_file():
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        relative = Path(pointer["directory"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("active model pointer is invalid")
        active_dir = model_path.parent / relative
        model_path = active_dir / "best_model.joblib"
        report_path = active_dir / "metrics.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if report.get("model_sha256") != model_hash:
        raise ValueError(
            "model artifact hash does not match its training report; retrain the model"
        )
    if report.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("training report uses an incompatible feature schema")
    selected_model = report.get("selected_model")
    if report.get("task") != "binary_classification" or not selected_model:
        raise ValueError("training report does not identify a selected binary classifier")
    if (
        selected_model not in report.get("candidates", {})
        or selected_model not in report.get("test_evaluation", {})
        or "average_precision" not in report["candidates"][selected_model].get("validation", {})
    ):
        raise ValueError("training report lacks validation and test metrics for its selected model")
    reference = report.get("explanation_reference")
    if not isinstance(reference, dict) or set(reference) != set(FEATURE_NAMES):
        raise ValueError("training report lacks the feature reference values for explanations")
    threshold = float(report.get("threshold", 0.5))
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("training report has an invalid classification threshold")
    return joblib.load(model_path), report, model_hash


async def _aggregate_window(
    connection: Any, reading: Any
) -> tuple[dict[str, float] | None, str | None]:
    end = reading["recorded_at"]
    tolerance = timedelta(seconds=reading["expected_interval_seconds"] * 1.5)
    boundary = reading["window_start"]
    coverage_tolerance = min(tolerance, timedelta(seconds=60))
    history = await connection.fetch(
        """
        SELECT recorded_at, cumulative_volume_liters, quality
        FROM telemetry_readings
        WHERE device_id = $1 AND recorded_at >= $2 AND recorded_at < $3
        ORDER BY recorded_at, id
        """,
        reading["device_id"], boundary - coverage_tolerance, end,
    )
    return transform_window(history, reading, MODEL_WINDOW_SECONDS)


async def run_batch(
    pool: Any,
    *,
    model: Any,
    report: dict[str, Any],
    model_version: str,
    batch_size: int = 100,
) -> int:
    """Score valid readings not yet processed by this model version."""
    async with pool.acquire() as connection:
        readings = await connection.fetch(
            """
            SELECT r.id, r.device_id, r.event_id, r.recorded_at, r.quality,
                   r.cumulative_volume_liters, r.flow_rate_liters_minute,
                   d.name AS device_name, d.property_id, d.expected_interval_seconds,
                   p.timezone, bucket.window_start
            FROM telemetry_readings AS r
            JOIN devices AS d ON d.id = r.device_id
            JOIN properties AS p ON p.id = d.property_id AND p.archived_at IS NULL
            CROSS JOIN LATERAL (
                SELECT date_bin(interval '5 minutes', r.recorded_at,
                                timestamptz '2000-01-01 00:00:00+00') AS window_start
            ) AS bucket
            WHERE r.quality = 'valid'
              AND (
                d.expected_interval_seconds >= 300 OR (
                  bucket.window_start + interval '5 minutes'
                      + d.expected_interval_seconds * interval '1 second' <= now()
                  AND NOT EXISTS (
                    SELECT 1 FROM telemetry_readings AS later
                    WHERE later.device_id = r.device_id AND later.quality = 'valid'
                      AND later.recorded_at < bucket.window_start + interval '5 minutes'
                      AND (later.recorded_at, later.id) > (r.recorded_at, r.id)
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM telemetry_readings AS earlier
                    JOIN ml_inferences AS i ON i.reading_id = earlier.id
                    WHERE earlier.device_id = r.device_id AND i.model_version = $1
                      AND earlier.recorded_at >= bucket.window_start
                      AND earlier.recorded_at < bucket.window_start + interval '5 minutes'
                  )
                )
              )
              AND NOT EXISTS (
                  SELECT 1 FROM ml_inferences AS i
                  WHERE i.reading_id = r.id AND i.model_version = $1
              )
            ORDER BY r.recorded_at, r.id
            LIMIT $2
            """,
            model_version,
            batch_size,
        )
        if not readings:
            return 0

        prepared: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for reading in readings:
            if reading["expected_interval_seconds"] < MODEL_WINDOW_SECONDS:
                if reading["timezone"] != report.get("timezone"):
                    features, reason = None, (
                        "Fuso da propriedade diferente do fuso usado no treinamento."
                    )
                else:
                    features, reason = await _aggregate_window(connection, reading)
                if features is not None:
                    prepared.append({
                        "reading": reading, "features": features,
                        "derivation": "cumulative_volume_5min_window",
                    })
                else:
                    pending.append({
                        "reading": reading, "status": "skipped", "predicted_anomaly": None,
                        "probability": None, "features": {},
                        "explanation": {"method": "not_scored", "reason": reason}, "reason": reason,
                    })
                continue
            previous = await connection.fetchrow(
                """
                SELECT recorded_at, cumulative_volume_liters, quality
                FROM telemetry_readings
                WHERE device_id = $1 AND recorded_at < $2
                ORDER BY recorded_at DESC
                LIMIT 1
                """,
                reading["device_id"],
                reading["recorded_at"],
            )
            reason = None
            feature_values = None
            if reading["timezone"] != report.get("timezone"):
                reason = "Fuso da propriedade diferente do fuso usado no treinamento."
            elif previous is None or previous["quality"] != "valid":
                reason = "Histórico insuficiente para calcular a variação do volume."
            else:
                elapsed = (reading["recorded_at"] - previous["recorded_at"]).total_seconds() / 60
                current_volume = reading["cumulative_volume_liters"]
                previous_volume = previous["cumulative_volume_liters"]
                measured_flow = reading["flow_rate_liters_minute"]
                derivation = "cumulative_volume"
                if elapsed <= 0:
                    reason = "Intervalo ou variação de volume incompatível com o treinamento."
                elif current_volume is not None and previous_volume is not None:
                    volume_delta = float(current_volume - previous_volume)
                    if measured_flow is None:
                        flow_rate = volume_delta / elapsed
                        derivation = "flow_rate_from_cumulative_volume"
                    else:
                        flow_rate = float(measured_flow)
                elif measured_flow is not None and elapsed <= (
                    float(reading["expected_interval_seconds"]) * 1.5 / 60
                ):
                    flow_rate = float(measured_flow)
                    volume_delta = flow_rate * elapsed
                    derivation = "volume_delta_estimated_from_flow"
                else:
                    reason = (
                        "Volume acumulado insuficiente e intervalo longo demais para estimar "
                        "a variação usando a vazão."
                    )

                if reason is None and volume_delta < 0:
                    reason = "Intervalo ou variação de volume incompatível com o treinamento."
                elif reason is None:
                    feature_values = transform_reading(
                        flow_rate_liters_minute=flow_rate,
                        volume_delta_liters=volume_delta,
                        elapsed_minutes=elapsed,
                        recorded_at=reading["recorded_at"],
                        timezone=reading["timezone"],
                    )
                    prepared.append(
                        {
                            "reading": reading,
                            "features": feature_values,
                            "derivation": derivation,
                        }
                    )
            if reason is not None:
                pending.append(
                    {
                        "reading": reading,
                        "status": "skipped",
                        "predicted_anomaly": None,
                        "probability": None,
                        "features": feature_values or {},
                        "explanation": {"method": "not_scored", "reason": reason},
                        "reason": reason,
                    }
                )

        if prepared:
            values = np.asarray(
                [[item["features"][name] for name in FEATURE_NAMES] for item in prepared],
                dtype=np.float64,
            )
            probabilities = model.predict_proba(values)[:, 1]
            invalid_probabilities = (probabilities < 0) | (probabilities > 1)
            if not np.isfinite(probabilities).all() or np.any(invalid_probabilities):
                raise ValueError("model produced invalid probabilities")
            reference = np.asarray(
                [float(report["explanation_reference"][name]) for name in FEATURE_NAMES],
                dtype=np.float64,
            )
            effects: list[np.ndarray] = []
            for feature_index in range(len(FEATURE_NAMES)):
                counterfactual = values.copy()
                counterfactual[:, feature_index] = reference[feature_index]
                effects.append(probabilities - model.predict_proba(counterfactual)[:, 1])
            threshold = float(report.get("threshold", 0.5))
            for row_index, item in enumerate(prepared):
                probability = float(probabilities[row_index])
                ranked_effects = sorted(
                    (
                        {
                            "feature": name,
                            "observed_value": item["features"][name],
                            "reference_value": float(reference[index]),
                            "probability_delta": round(float(effects[index][row_index]), 6),
                        }
                        for index, name in enumerate(FEATURE_NAMES)
                    ),
                    key=lambda effect: abs(effect["probability_delta"]),
                    reverse=True,
                )
                pending.append(
                    {
                        "reading": item["reading"],
                        "status": "scored",
                        "predicted_anomaly": probability >= threshold,
                        "probability": probability,
                        "features": item["features"],
                        "explanation": {
                            "method": "single_feature_replacement_vs_training_median",
                            "classification_threshold": threshold,
                            "input_derivation": item["derivation"],
                            "top_signals": ranked_effects[:3],
                            "interpretation": (
                                "Sensitivity estimate, not causal attribution; replacing one "
                                "feature at a time with its training median can change "
                                "correlated inputs."
                            ),
                        },
                        "reason": (
                            f"Avaliação experimental: probabilidade estimada de anomalia "
                            f"{probability:.1%}. Previsões consecutivas podem gerar um alerta "
                            "experimental separado das regras."
                        ),
                    }
                )

        async with connection.transaction():
            for item in pending:
                reading = item["reading"]
                inference_id = uuid4()
                inserted_id = await connection.fetchval(
                    """
                    INSERT INTO ml_inferences (
                        id, reading_id, model_version, status, predicted_anomaly,
                        anomaly_probability, feature_values, explanation, reason, inferred_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7::json, $8::json, $9, $10)
                    ON CONFLICT (reading_id, model_version) DO NOTHING
                    RETURNING id
                    """,
                    inference_id,
                    reading["id"],
                    model_version,
                    item["status"],
                    item["predicted_anomaly"],
                    item["probability"],
                    json.dumps(item["features"], allow_nan=False),
                    json.dumps(item["explanation"], allow_nan=False),
                    item["reason"],
                    datetime.now(UTC),
                )
                if inserted_id is not None and item["predicted_anomaly"] is True:
                    probability = float(item["probability"])
                    explanation = item["explanation"]
                    await _record_ml_alert(
                        connection,
                        inference_id=inserted_id,
                        reading=reading,
                        model_version=model_version,
                        probability=probability,
                        threshold=float(
                            explanation.get(
                                "classification_threshold", report.get("threshold", 0.5)
                            )
                        ),
                        features=item["features"],
                        explanation=explanation,
                        reason=(
                            "O modelo experimental identificou comportamento compatível com "
                            f"anomalia ({probability:.1%} de probabilidade). Verifique as "
                            "evidências; este alerta não substitui as regras de monitoramento."
                        ),
                    )
        return len(pending)


async def serve() -> None:
    import asyncpg

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    database_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    model_path = Path(os.getenv("ML_MODEL_PATH", "data/ml/training-bench-v2/best_model.joblib"))
    report_path = Path(
        os.getenv("ML_TRAINING_REPORT_PATH", "data/ml/training-bench-v2/metrics.json")
    )
    poll_seconds = max(1, int(os.getenv("ML_POLL_SECONDS", "5")))
    model, report, version = load_model(model_path, report_path)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    now = datetime.now(UTC).isoformat()
    with _health_lock:
        _health.update(
            status="healthy",
            model_name=report["selected_model"],
            model_version=version,
            started_at=now,
            last_check_at=now,
        )
    _start_health_server()
    logger.info(
        "Loaded experimental model %s version %s",
        report["selected_model"],
        version,
    )
    try:
        while True:
            try:
                refreshed_model, refreshed_report, refreshed_version = load_model(model_path, report_path)
                if refreshed_version != version:
                    model, report, version = refreshed_model, refreshed_report, refreshed_version
                    with _health_lock:
                        _health["model_name"] = report["selected_model"]
                        _health["model_version"] = version
                    logger.info("Activated experimental model %s version %s", report["selected_model"], version)
                processed = await run_batch(pool, model=model, report=report, model_version=version)
                with _health_lock:
                    _health["status"] = "healthy"
                    _health["last_check_at"] = datetime.now(UTC).isoformat()
                    _health["processed_records"] = int(_health["processed_records"]) + processed
                if processed:
                    logger.info("Persisted %d inference records", processed)
            except Exception:
                with _health_lock:
                    _health["status"] = "degraded"
                    _health["last_check_at"] = datetime.now(UTC).isoformat()
                    _health["failed_batches"] = int(_health["failed_batches"]) + 1
                logger.exception("Inference batch failed; rule-based monitoring remains active")
            await asyncio.sleep(poll_seconds)
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="process one batch and exit")
    args = parser.parse_args()
    if args.once:
        asyncio.run(_run_once())
    else:
        asyncio.run(serve())


async def _run_once() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    model, report, version = load_model(
        Path(os.getenv("ML_MODEL_PATH", "data/ml/training-bench-v2/best_model.joblib")),
        Path(os.getenv("ML_TRAINING_REPORT_PATH", "data/ml/training-bench-v2/metrics.json")),
    )
    import asyncpg

    database_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
    try:
        processed = await run_batch(pool, model=model, report=report, model_version=version)
        print(
            json.dumps(
                {"model_version": version, "processed": processed},
                sort_keys=True,
            )
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    main()
