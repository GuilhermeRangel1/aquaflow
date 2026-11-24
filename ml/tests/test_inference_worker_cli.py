"""Acceptance checks for the inference worker's model loading gate."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_worker_refuses_a_model_without_a_matching_versioned_report(tmp_path: Path) -> None:
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"untrusted model artifact")
    report_path = tmp_path / "metrics.json"
    report_path.write_text(
        json.dumps(
            {
                "model_sha256": hashlib.sha256(b"another artifact").hexdigest(),
                "feature_names": [],
            }
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ML_MODEL_PATH": str(model_path),
            "ML_TRAINING_REPORT_PATH": str(report_path),
            "DATABASE_URL": "postgresql+asyncpg://unused",
        }
    )

    result = subprocess.run(
        [sys.executable, "ml/inference_worker.py", "--once"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "hash does not match" in result.stderr


@pytest.mark.asyncio
async def test_worker_keeps_processing_after_rejected_update(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(ROOT / "ml"))
    import inference_worker as worker

    artifact_hash = "a" * 64
    original = worker.inference_version(artifact_hash, 0.5)
    updated = worker.inference_version(artifact_hash, 0.75)
    assert original == artifact_hash
    assert updated != original
    assert updated == worker.inference_version(artifact_hash, 0.75)

    reports = iter(((original, False), (original, True), (updated, False)))

    def load(*_args):
        version, invalid = next(reports)
        if invalid:
            raise ValueError("invalid candidate")
        return object(), {"selected_model": "knn"}, version

    async def close():
        pass

    async def create_pool(*_args, **_kwargs):
        return SimpleNamespace(close=close)

    seen = []

    async def run_batch(*_args, model_version, **_kwargs):
        seen.append((model_version, worker._health["model_update_rejected"]))
        return 1

    async def sleep(_seconds):
        if len(seen) == 2:
            raise asyncio.CancelledError

    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(worker, "_health", worker._health.copy())
    monkeypatch.setattr(worker, "_start_health_server", lambda: None)
    monkeypatch.setattr(worker, "load_model", load)
    monkeypatch.setattr(worker, "run_batch", run_batch)
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    import asyncpg

    monkeypatch.setattr(asyncpg, "create_pool", create_pool)
    with pytest.raises(asyncio.CancelledError):
        await worker.serve()
    assert seen == [(original, True), (updated, False)]
