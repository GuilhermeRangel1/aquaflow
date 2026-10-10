"""Acceptance test for the offline train-and-predict workflow."""

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")


def _generate_and_prepare(raw: Path, prepared: Path, start: str, seed: str, days: str) -> None:
    _run(
        "ml/generate_mock_data.py",
        "--output",
        str(raw),
        "--seed",
        seed,
        "--start",
        start,
        "--timezone",
        "America/Sao_Paulo",
        "--days",
        days,
    )
    _run(
        "ml/prepare_dataset.py",
        "prepare",
        "--input",
        str(raw),
        "--output-dir",
        str(prepared),
        "--timezone",
        "America/Sao_Paulo",
    )


def test_cli_reuses_preparation_and_predicts_with_a_versioned_model(tmp_path: Path) -> None:
    training_raw = tmp_path / "training-raw.csv"
    training_prepared = tmp_path / "training-prepared"
    model_dir = tmp_path / "model"
    tracking = f"sqlite:///{(tmp_path / 'mlflow.db').resolve().as_posix()}"
    _generate_and_prepare(
        training_raw,
        training_prepared,
        "2026-09-01T00:00:00-03:00",
        "42",
        "16",
    )
    _run(
        "ml/train_model.py",
        "--features",
        str(training_prepared / "features.csv"),
        "--labels",
        str(training_prepared / "labels.csv"),
        "--metadata",
        str(training_prepared / "metadata.csv"),
        "--output-dir",
        str(model_dir),
        "--tracking-uri",
        tracking,
        "--experiment-name",
        "inference-acceptance-test",
        "--search-iterations",
        "1",
    )

    inference_raw = tmp_path / "inference-raw.csv"
    inference_prepared = tmp_path / "inference-prepared"
    _generate_and_prepare(
        inference_raw,
        inference_prepared,
        "2026-09-17T00:00:00-03:00",
        "99",
        "4",
    )
    output = tmp_path / "predictions"
    _run(
        "ml/predict_model.py",
        "--features",
        str(inference_prepared / "features.csv"),
        "--metadata",
        str(inference_prepared / "metadata.csv"),
        "--preparation-manifest",
        str(inference_prepared / "preparation_manifest.json"),
        "--model",
        str(model_dir / "best_model.joblib"),
        "--training-report",
        str(model_dir / "metrics.json"),
        "--output-dir",
        str(output),
    )

    training_report = json.loads((model_dir / "metrics.json").read_text(encoding="utf-8"))
    prediction_manifest = json.loads(
        (output / "prediction_manifest.json").read_text(encoding="utf-8")
    )
    expected_hash = hashlib.sha256((model_dir / "best_model.joblib").read_bytes()).hexdigest()
    assert training_report["model_sha256"] == expected_hash
    assert training_report["generalization_validation"]["profile"] == "shifted"
    assert training_report["stress_test_evaluation"]["profile"] == "stress"
    assert (model_dir / "training_report.md").is_file()
    assert prediction_manifest["model_version"] == expected_hash
    assert prediction_manifest["timezone"] == "America/Sao_Paulo"
    assert prediction_manifest["prediction_count"] == 1127

    with (output / "predictions.csv").open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
    assert reader.fieldnames == [
        "event_id",
        "recorded_at",
        "predicted_anomaly",
        "anomaly_probability",
        "model_version",
        "feature_effects_json",
    ]
    assert len(rows) == 1127
    assert {row["predicted_anomaly"] for row in rows} <= {"0", "1"}
    assert {row["model_version"] for row in rows} == {expected_hash}
    assert all(0 <= float(row["anomaly_probability"]) <= 1 for row in rows)
    assert all(len(json.loads(row["feature_effects_json"])) == 7 for row in rows)
