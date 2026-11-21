"""Acceptance tests for the offline ML training command."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")


@pytest.mark.parametrize("future_profile", [False, True])
def test_cli_compares_models_on_chronological_holdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, future_profile: bool
) -> None:
    raw = tmp_path / "raw.csv"
    prepared = tmp_path / "prepared"
    shifted_raw = tmp_path / "shifted_raw.csv"
    shifted_prepared = tmp_path / "shifted_prepared"
    stress_raw = tmp_path / "stress_raw.csv"
    stress_prepared = tmp_path / "stress_prepared"
    output = tmp_path / "training"
    tracking = f"sqlite:///{(tmp_path / 'mlflow.db').resolve().as_posix()}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))

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
    for profile, seed, raw_path, prepared_path in (
        ("shifted", "99", shifted_raw, shifted_prepared),
        ("stress", "202", stress_raw, stress_prepared),
    ):
        _run(
            "ml/generate_mock_data.py",
            "--output",
            str(raw_path),
            "--seed",
            seed,
            "--start",
            (
                "2026-08-01T00:00:00-03:00"
                if profile == "shifted" and not future_profile
                else "2026-11-01T00:00:00-03:00"
            ),
            "--timezone",
            "America/Sao_Paulo",
            "--profile",
            profile,
        )
        _run(
            "ml/prepare_dataset.py",
            "prepare",
            "--input",
            str(raw_path),
            "--output-dir",
            str(prepared_path),
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

    training_command = (
        "ml/train_model.py",
        "--features",
        str(prepared / "features.csv"),
        "--labels",
        str(prepared / "labels.csv"),
        "--metadata",
        str(prepared / "metadata.csv"),
        "--output-dir",
        str(output),
        "--experiment-name",
        "acceptance-test",
        "--search-iterations",
        "1",
        "--generalization-validation-features",
        str(shifted_prepared / "features.csv"),
        "--generalization-validation-labels",
        str(shifted_prepared / "labels.csv"),
        "--generalization-validation-metadata",
        str(shifted_prepared / "metadata.csv"),
        "--stress-test-features",
        str(stress_prepared / "features.csv"),
        "--stress-test-labels",
        str(stress_prepared / "labels.csv"),
        "--stress-test-metadata",
        str(stress_prepared / "metadata.csv"),
    )
    if future_profile:
        with pytest.raises(AssertionError, match="anteriores ao início do teste"):
            _run(*training_command)
        assert not (output / "best_model.joblib").exists()
        return
    _run(*training_command)

    report = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert report["task"] == "binary_classification"
    assert report["target"] == "anomaly_label"
    assert report["timezone"] == "America/Sao_Paulo"
    assert report["split_counts"] == {"train": 2255, "validation": 1128, "test": 1128}
    assert set(report["candidates"]) == {"dummy_prior", "knn", "decision_tree", "random_forest"}
    assert report["selected_model"] in {"knn", "decision_tree", "random_forest"}
    for candidate in report["candidates"].values():
        metrics = candidate["validation"]
        assert 0.0 <= metrics["average_precision"] <= 1.0
        assert len(metrics["confusion_matrix"]) == 2
        assert all(len(row) == 2 for row in metrics["confusion_matrix"])
        if "cv_folds" in candidate:
            assert len(candidate["cv_folds"]) == 3
            assert all(
                0.0 <= fold["validation_average_precision"] <= 1.0
                for fold in candidate["cv_folds"]
            )
    assert set(report["test_evaluation"]) == {report["selected_model"], "dummy_prior"}
    curves = report["evaluation_curves"]
    assert len(curves["test"]["precision_recall"]["recall"]) > 2
    assert len(curves["test"]["roc"]["false_positive_rate"]) > 2
    assert 0.0 <= curves["test"]["roc_auc"] <= 1.0
    assert len(curves["stress"]["roc"]["true_positive_rate"]) > 2
    assert set(report["generalization_validation"]) == {
        "profile",
        "data_sha256",
        "sample_count",
        "candidates",
    }
    assert report["generalization_validation"]["profile"] == "shifted"
    assert report["generalization_validation"]["data_sha256"] != report["training_data_sha256"]
    assert len(report["final_training_data_sha256"]) == 64
    assert set(report["stress_test_evaluation"]) == {
        "profile",
        "data_sha256",
        "sample_count",
        "selected_model",
        "dummy_prior",
    }
    assert report["stress_test_evaluation"]["profile"] == "stress"
    assert report["overfitting_diagnostics"]["cv_generalization_gap"] is not None
    assert report["overfitting_diagnostics"]["domain_shift_assessment"] in {
        "sensitivity_detected",
        "no_large_validation_gap_detected",
    }
    assert (output / "best_model.joblib").is_file()
    assert (output / "training_report.md").is_file()
    assert "Hash combinado dos dados" in (output / "training_report.md").read_text(encoding="utf-8")
    assert (output / "split_manifest.json").is_file()
    assert (tmp_path / "mlflow.db").is_file()

    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking)
    runs = client.search_runs([report["mlflow_experiment_id"]])
    summaries = {run.info.run_id: run.info.run_name for run in runs}
    trials = [run for run in runs if "mlflow.parentRunId" in run.data.tags]
    assert len(trials) == 3
    for trial in trials:
        parent_name = summaries[trial.data.tags["mlflow.parentRunId"]]
        assert trial.data.params["model"] == parent_name
        assert trial.data.params["data_sha256"] == report["training_data_sha256"]
        assert trial.data.tags["selected_for_model"] == "true"
        for partition in ("train", "validation"):
            history = client.get_metric_history(
                trial.info.run_id, f"cv_{partition}_average_precision"
            )
            assert sorted(metric.step for metric in history) == [1, 2, 3]


def test_hybrid_candidates_generalize_without_a_large_training_gap(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    prepared = tmp_path / "prepared"
    output = tmp_path / "training"
    _run(
        "ml/build_real_dataset.py",
        "--calibration",
        "--output",
        str(raw),
        "--start",
        "2026-09-01T00:00:00-03:00",
        "--seed",
        "42",
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
        f"sqlite:///{(tmp_path / 'mlflow.db').resolve().as_posix()}",
    )
    report = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    baseline_ap = report["candidates"]["dummy_prior"]["validation"]["average_precision"]
    for name in ("knn", "random_forest", "decision_tree"):
        candidate = report["candidates"][name]
        assert candidate["cv_generalization_gap"] < 0.1, name
        assert candidate["cv_validation_average_precision_std"] < 0.1, name
        assert candidate["validation"]["average_precision"] > baseline_ap + 0.2, name
        holdout = report["candidate_holdout_evaluation"][name]
        assert holdout["stress"]["recall"] > 0.8, name
        assert holdout["test"]["average_precision"] > 0.85, name
        assert (output / "candidate-models" / f"{name}.joblib").is_file()
    assert report["final_training_end"] < report["test_start"]
