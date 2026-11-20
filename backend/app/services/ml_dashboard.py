"""Read-only model training data used by the technical dashboard."""

import asyncio
import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.schemas.ml_dashboard import ActiveModelSummary


class TrainingDashboardUnavailable(Exception):
    """The active training report and model artifact are missing or inconsistent."""


def _decode_json_object(contents: bytes) -> dict[str, Any]:
    payload = json.loads(contents)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise ValueError("Expected JSON object keys to be strings")
        result[key] = value
    return result


def load_active_training_report(artifacts_dir: Path) -> tuple[dict[str, Any], str]:
    training_dir = artifacts_dir / "training-bench-v2"
    try:
        pointer = json.loads((training_dir / "active-model.json").read_text(encoding="utf-8"))
        candidate = Path(pointer["directory"])
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("Invalid active model pointer")
        training_dir = training_dir / candidate
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise TrainingDashboardUnavailable from None
    report_path = training_dir / "metrics.json"
    model_path = training_dir / "best_model.joblib"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    except (OSError, json.JSONDecodeError):
        raise TrainingDashboardUnavailable from None
    if not isinstance(report, dict) or report.get("model_sha256") != model_hash:
        raise TrainingDashboardUnavailable
    if not isinstance(report.get("selected_model"), str) or not isinstance(
        report.get("threshold"), (int, float)
    ):
        raise TrainingDashboardUnavailable
    return report, model_hash


def active_model_summary(report: dict[str, Any], model_hash: str) -> ActiveModelSummary:
    trained_at = report.get("final_training_end")
    if isinstance(trained_at, str):
        try:
            trained_at = datetime.fromisoformat(trained_at.replace("Z", "+00:00"))
        except ValueError:
            trained_at = None
    else:
        trained_at = None
    return ActiveModelSummary(
        key=report["selected_model"],
        version=model_hash,
        trained_at=trained_at,
        threshold=float(report["threshold"]),
    )


def _mlflow_json(uri: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{uri.rstrip('/')}{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return _decode_json_object(response.read())


def _list_mlflow_executions(uri: str, experiment_id: str) -> list[dict[str, Any]]:
    all_runs: list[dict[str, Any]] = []
    page_token: str | None = None
    for _ in range(10):
        query: dict[str, Any] = {
            "experiment_ids": [experiment_id],
            "max_results": 1000,
            "order_by": ["attributes.start_time DESC"],
        }
        if page_token:
            query["page_token"] = page_token
        result = _mlflow_json(uri, "/api/2.0/mlflow/runs/search", query)
        all_runs.extend(result.get("runs", []))
        page_token = result.get("next_page_token")
        if not page_token:
            break

    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in all_runs:
        info = run.get("info", {})
        data = run.get("data", {})
        tags = {item.get("key"): item.get("value") for item in data.get("tags", [])}
        params = {item.get("key"): item.get("value") for item in data.get("params", [])}
        if tags.get("mlflow.parentRunId") or info.get("status") != "FINISHED":
            continue
        execution_id = tags.get("airflow_run_id") or info.get("run_id")
        grouped.setdefault(execution_id, []).append(
            {
                "run_id": info.get("run_id"),
                "model": params.get("model") or info.get("run_name", "Modelo"),
                "model_sha256": params.get("model_sha256"),
                "started_at": info.get("start_time"),
                "metrics": data.get("metrics", []),
            }
        )

    executions = []
    for execution_id, candidates in grouped.items():
        selected = next((item for item in candidates if item["model_sha256"]), None)
        if selected is None:
            continue
        started_at = max((item["started_at"] or 0) for item in candidates)
        executions.append(
            {
                "id": execution_id,
                "run_id": selected["run_id"] if selected else candidates[0]["run_id"],
                "model": selected["model"] if selected else candidates[0]["model"],
                "model_version": selected["model_sha256"] if selected else None,
                "started_at": (
                    datetime.fromtimestamp(started_at / 1000, tz=UTC)
                    .isoformat()
                    .replace("+00:00", "Z")
                    if started_at
                    else None
                ),
                "candidate_count": len(candidates),
            }
        )
    return sorted(executions, key=lambda item: item["started_at"] or "", reverse=True)


async def list_mlflow_executions(
    tracking_uri: str | None, experiment_id: str | None
) -> list[dict[str, Any]]:
    if not tracking_uri or not experiment_id:
        return []
    try:
        return await asyncio.to_thread(_list_mlflow_executions, tracking_uri, experiment_id)
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        ValueError,
        KeyError,
        TypeError,
    ):
        return []


def _read_ml_worker_status(url: str | None) -> str:
    if not url:
        return "unavailable"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = _decode_json_object(response.read())
    except (OSError, ValueError, urllib.error.URLError, TimeoutError):
        return "unavailable"
    status = payload.get("status")
    return status if status in {"healthy", "degraded", "starting"} else "unavailable"


async def ml_worker_status(url: str | None) -> str:
    return await asyncio.to_thread(_read_ml_worker_status, url)


def _load_execution_report(artifacts_dir: Path, run_id: str) -> dict[str, Any]:
    if not run_id or Path(run_id).name != run_id:
        raise TrainingDashboardUnavailable
    training_dir = artifacts_dir / "training-bench-v2"
    report_paths = [training_dir / "mlflow-artifacts" / run_id / "artifacts" / "metrics.json"]
    candidates = training_dir / "candidates"
    if candidates.is_dir():
        report_paths.extend(candidates.glob(f"*/mlflow-artifacts/{run_id}/artifacts/metrics.json"))
    report_path = next((path for path in report_paths if path.is_file()), report_paths[0])
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise TrainingDashboardUnavailable from None
    if not isinstance(report, dict):
        raise TrainingDashboardUnavailable
    return report


async def load_mlflow_execution_report(artifacts_dir: Path, run_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_load_execution_report, artifacts_dir, run_id)
    except TrainingDashboardUnavailable:
        raise
