"""Acceptance tests for the offline ML training command."""

import csv
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


def test_cli_compares_models_on_chronological_holdout(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    prepared = tmp_path / "prepared"
    output = tmp_path / "training"
    tracking = f"sqlite:///{(tmp_path / 'mlflow.db').resolve().as_posix()}"

    _run(
        "ml/generate_mock_data.py",
        "--output",
        str(raw),
        "--start",
        "2026-09-01T00:00:00-03:00",
        "--timezone",
        "America/Sao_Paulo",
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

    with (prepared / "features.csv").open(newline="", encoding="utf-8") as source:
        feature_names = next(csv.reader(source))
    assert feature_names == [
        "flow_rate_liters_minute",
        "volume_delta_liters",
        "elapsed_minutes",
        "local_hour_sin",
        "local_hour_cos",
        "local_weekday_sin",
        "local_weekday_cos",
    ]

    _run(
        "ml/train_model.py",
        "--features",
        str(prepared / "features.csv"),
        "--labels",
        str(prepared / "labels.csv"),
        "--metadata",
        str(prepared / "metadata.csv"),
        "--output-dir",
        str(output),
        "--tracking-uri",
        tracking,
        "--experiment-name",
        "acceptance-test",
        "--search-iterations",
        "1",
    )

    report = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert report["task"] == "binary_classification"
    assert report["target"] == "anomaly_label"
    assert report["timezone"] == "America/Sao_Paulo"
    assert report["split_counts"] == {"train": 2255, "validation": 1128, "test": 1128}
    assert len(report["candidates"]) == 4  # baseline plus three model families
    assert report["selected_model"] in {"logistic_regression", "random_forest", "hist_gradient_boosting"}
    for candidate in report["candidates"].values():
        metrics = candidate["validation"]
        assert 0.0 <= metrics["average_precision"] <= 1.0
        assert len(metrics["confusion_matrix"]) == 2
        assert all(len(row) == 2 for row in metrics["confusion_matrix"])
    assert set(report["test_evaluation"]) == {report["selected_model"], "dummy_prior"}
    assert (output / "best_model.joblib").is_file()
    assert (output / "split_manifest.json").is_file()
    assert (tmp_path / "mlflow.db").is_file()
