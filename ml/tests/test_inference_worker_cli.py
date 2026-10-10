"""Acceptance checks for the inference worker's model loading gate."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

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
