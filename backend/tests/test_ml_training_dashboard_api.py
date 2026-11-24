import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import current_user
from app.core.config import Settings
from app.main import create_app


def _dashboard_client(artifacts_dir: Path, mlflow_uri: str | None = None) -> AsyncClient:
    app = create_app(
        settings=Settings(ml_artifacts_dir=artifacts_dir, mlflow_tracking_uri=mlflow_uri)
    )
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(email="viewer@example.com")
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_authenticated_dashboard_returns_active_model_report(tmp_path: Path) -> None:
    model_artifact = tmp_path / "training-bench-v2" / "best_model.joblib"
    model_artifact.parent.mkdir(parents=True)
    model_artifact.write_bytes(b"test artifact")
    report = {
        "selected_model": "knn",
        "model_sha256": hashlib.sha256(model_artifact.read_bytes()).hexdigest(),
        "final_training_end": "2026-09-13T02:55:00+00:00",
        "trained_at": "2026-11-24T14:00:00+00:00",
        "threshold": 0.5,
        "candidates": {"knn": {"validation": {"average_precision": 0.97}}},
    }
    artifact = tmp_path / "training-bench-v2" / "metrics.json"
    artifact.write_text(
        json.dumps({**report, "development": {"source": {"device_id": "private-device"}}}),
        encoding="utf-8",
    )

    async with _dashboard_client(tmp_path) as client:
        response = await client.get("/api/v1/ml/training-dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["active_model"] == {
        "key": "knn",
        "version": report["model_sha256"],
        "trained_at": "2026-11-24T14:00:00Z",
        "threshold": 0.5,
    }
    assert body["history_available"] is False
    assert body["worker_status"] == "unavailable"
    assert body["executions"] == []
    assert body["selected_execution_id"] is None
    assert body["report"] == report
    assert body["active_report"] == report


@pytest.mark.asyncio
async def test_dashboard_reports_unavailable_when_active_artifact_is_missing(
    tmp_path: Path,
) -> None:
    async with _dashboard_client(tmp_path) as client:
        response = await client.get("/api/v1/ml/training-dashboard")

    assert response.status_code == 503
    assert response.json()["code"] == "ml_dashboard_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("history_unavailable", [False, True])
async def test_dashboard_distinguishes_missing_execution_from_unavailable_history(
    tmp_path: Path, monkeypatch, history_unavailable: bool
) -> None:
    model_artifact = tmp_path / "training-bench-v2" / "best_model.joblib"
    model_artifact.parent.mkdir(parents=True)
    model_artifact.write_bytes(b"test artifact")
    report = {
        "selected_model": "knn",
        "model_sha256": hashlib.sha256(model_artifact.read_bytes()).hexdigest(),
        "threshold": 0.5,
    }
    (model_artifact.parent / "metrics.json").write_text(json.dumps(report), encoding="utf-8")

    async def executions(*_args):
        if history_unavailable:
            return None
        return [
            {
                "id": "known-run",
                "run_id": "internal-run-id",
                "model": "knn",
                "model_version": report["model_sha256"],
                "started_at": None,
                "candidate_count": 4,
            }
        ]

    monkeypatch.setattr("app.api.ml_dashboard.list_mlflow_executions", executions)
    async with _dashboard_client(tmp_path) as client:
        response = await client.get("/api/v1/ml/training-dashboard?execution_id=unknown-run")

    if history_unavailable:
        assert response.status_code == 503
        assert response.json()["code"] == "ml_execution_history_unavailable"
    else:
        assert response.status_code == 404
        assert response.json()["code"] == "ml_execution_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize("same_hash", [False, True])
async def test_dashboard_loads_selected_history_without_changing_active_model(
    tmp_path: Path, monkeypatch, same_hash: bool
) -> None:
    model_artifact = tmp_path / "training-bench-v2" / "best_model.joblib"
    model_artifact.parent.mkdir(parents=True)
    model_artifact.write_bytes(b"active model")
    active_hash = hashlib.sha256(model_artifact.read_bytes()).hexdigest()
    active_report = {
        "selected_model": "knn",
        "model_sha256": active_hash,
        "mlflow_experiment_id": "2",
        "threshold": 0.5,
    }
    (model_artifact.parent / "metrics.json").write_text(json.dumps(active_report), encoding="utf-8")
    history_report = {"selected_model": "decision_tree", "threshold": 0.5}

    async def executions(*_args):
        return [
            {
                "id": "historical-execution",
                "run_id": "internal-run-id",
                "model": "decision_tree",
                "model_version": active_hash if same_hash else "older-hash",
                "started_at": "2026-10-01T12:00:00Z",
                "candidate_count": 4,
            }
        ]

    async def historical_report(artifacts_dir: Path, run_id: str, tracking_uri, experiment_id):
        assert tracking_uri == "http://mlflow:5000" and experiment_id == "2"
        assert artifacts_dir == tmp_path
        assert run_id == "internal-run-id"
        return history_report

    monkeypatch.setattr("app.api.ml_dashboard.list_mlflow_executions", executions)
    monkeypatch.setattr("app.api.ml_dashboard.load_mlflow_execution_report", historical_report)
    async with _dashboard_client(tmp_path, "http://mlflow:5000") as client:
        response = await client.get(
            "/api/v1/ml/training-dashboard?execution_id=historical-execution"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["active_model"]["key"] == "knn"
    assert body["selected_execution_id"] == "historical-execution"
    assert body["report"] == history_report
    assert "run_id" not in body["executions"][0]


@pytest.mark.asyncio
async def test_training_dashboard_requires_authentication(
    empty_api_client: AsyncClient,
) -> None:
    response = await empty_api_client.get("/api/v1/ml/training-dashboard")

    assert response.status_code == 401


def test_worker_status_reads_only_known_health_state(monkeypatch) -> None:
    from app.services import ml_dashboard

    class Response:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    monkeypatch.setattr(
        ml_dashboard.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(b'{"status":"healthy","model_name":"private"}'),
    )
    assert ml_dashboard._read_ml_worker_status("http://worker/health") == "healthy"

    monkeypatch.setattr(
        ml_dashboard.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(b'{"status":"private-details"}'),
    )
    assert ml_dashboard._read_ml_worker_status("http://worker/health") == "unavailable"
    assert ml_dashboard._read_ml_worker_status(None) == "unavailable"


def test_history_loads_report_from_mlflow_server(tmp_path: Path, monkeypatch) -> None:
    from app.services import ml_dashboard

    run_id = "a" * 32

    def fetch(uri: str, path: str) -> dict[str, str]:
        assert uri == "http://mlflow:5000"
        assert path == f"/api/2.0/mlflow-artifacts/artifacts/2/{run_id}/artifacts/metrics.json"
        return {"mlflow_run_id": run_id, "selected_model": "knn"}

    monkeypatch.setattr(ml_dashboard, "_mlflow_json", fetch)
    assert ml_dashboard._load_run_report(tmp_path, run_id, "http://mlflow:5000", "2") == {
        "mlflow_run_id": run_id,
        "selected_model": "knn",
    }


def test_history_reports_missing_when_mlflow_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    from app.services import ml_dashboard

    def unavailable(*_args: str) -> None:
        raise OSError("MLflow unavailable")

    monkeypatch.setattr(ml_dashboard, "_mlflow_json", unavailable)
    with pytest.raises(ml_dashboard.TrainingDashboardUnavailable):
        ml_dashboard._load_run_report(tmp_path, "a" * 32, "http://mlflow:5000", "2")


@pytest.mark.asyncio
async def test_training_job_rejects_regular_authenticated_account(tmp_path: Path) -> None:
    from uuid import uuid4

    app = create_app(
        settings=Settings(ml_artifacts_dir=tmp_path, root_user_email="root@example.com")
    )
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(
        id=uuid4(), email="regular@example.com"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/ml/training-jobs")
    assert response.status_code == 403
    assert response.json()["code"] == "admin_required"


@pytest.mark.asyncio
async def test_public_registration_cannot_claim_root_email(tmp_path: Path) -> None:
    app = create_app(
        settings=Settings(ml_artifacts_dir=tmp_path, root_user_email="root@example.com")
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Tentativa de cadastro root",
                "email": "ROOT@example.com",
                "password": "test-password-with-12",
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "root_account_reserved"
