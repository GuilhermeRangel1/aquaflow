"""Compare reproducible anomaly classifiers on time-ordered mock telemetry."""

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import joblib
import mlflow
import numpy as np
from mlflow import MlflowClient
from sklearn.base import ClassifierMixin, clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import ParameterSampler, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES = (
    "flow_rate_liters_minute",
    "volume_delta_liters",
    "elapsed_minutes",
    "local_hour_sin",
    "local_hour_cos",
    "local_weekday_sin",
    "local_weekday_cos",
)
TARGET_NAME = "anomaly_label"
DEFAULT_TIMEZONE = "America/Sao_Paulo"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _load_dataset(
    features_path: Path, labels_path: Path, metadata_path: Path, timezone: str
) -> tuple[np.ndarray, np.ndarray, list[datetime], str]:
    features = _read_csv(features_path)
    labels = _read_csv(labels_path)
    metadata = _read_csv(metadata_path)
    if not features or len(features) != len(labels) or len(labels) != len(metadata):
        raise ValueError("features, labels e metadata devem ter o mesmo número de amostras")
    if set(features[0]) != set(FEATURE_NAMES):
        raise ValueError(f"features devem conter exatamente: {', '.join(FEATURE_NAMES)}")
    if any(set(row) != set(FEATURE_NAMES) for row in features):
        raise ValueError("schema inconsistente no arquivo de features")
    if any(set(row) != {"event_id", "scenario_label", TARGET_NAME} for row in labels):
        raise ValueError("schema inválido no arquivo de labels")
    if any(set(row) != {"event_id", "recorded_at", "device_serial"} for row in metadata):
        raise ValueError("schema inválido no arquivo de metadata")

    event_ids = [row["event_id"] for row in labels]
    if len(event_ids) != len(set(event_ids)) or event_ids != [row["event_id"] for row in metadata]:
        raise ValueError("event_id deve ser único e alinhar labels e metadata")

    try:
        ZoneInfo(timezone)
        parsed_timestamps = [
            datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
            for row in metadata
        ]
        if any(timestamp.tzinfo is None or timestamp.utcoffset() is None for timestamp in parsed_timestamps):
            raise ValueError("recorded_at deve incluir fuso horário")
        timestamps = [timestamp.astimezone(UTC) for timestamp in parsed_timestamps]
        targets = np.asarray([int(row[TARGET_NAME]) for row in labels], dtype=np.int8)
        values = np.asarray(
            [[float(row[name]) for name in FEATURE_NAMES] for row in features], dtype=np.float64
        )
    except (ValueError, TypeError, OverflowError, ZoneInfoNotFoundError) as error:
        raise ValueError(f"dataset preparado inválido: {error}") from error
    if not np.isfinite(values).all() or not np.isin(targets, (0, 1)).all():
        raise ValueError("features devem ser finitas e anomaly_label deve ser binário")
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("metadata deve estar em ordem cronológica, sem timestamps duplicados")
    if set(targets) != {0, 1}:
        raise ValueError("dataset precisa conter amostras normais e anômalas")

    fingerprint = hashlib.sha256()
    for path in (features_path, labels_path, metadata_path):
        fingerprint.update(path.read_bytes())
    return values, targets, timestamps, fingerprint.hexdigest()


def _split_indices(timestamps: list[datetime], timezone: str) -> dict[str, np.ndarray]:
    try:
        local_timezone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown IANA timezone: {timezone}") from error
    first_local = timestamps[0].astimezone(local_timezone)
    origin = datetime.combine(first_local.date(), time.min, tzinfo=local_timezone)
    train_end = (origin + timedelta(days=8)).astimezone(UTC)
    validation_end = (origin + timedelta(days=12)).astimezone(UTC)
    train = np.asarray([i for i, timestamp in enumerate(timestamps) if timestamp < train_end])
    validation = np.asarray(
        [i for i, timestamp in enumerate(timestamps) if train_end <= timestamp < validation_end]
    )
    test = np.asarray([i for i, timestamp in enumerate(timestamps) if timestamp >= validation_end])
    splits = {"train": train, "validation": validation, "test": test}
    for name, indices in splits.items():
        if not len(indices):
            raise ValueError(f"partição {name} vazia")
        if len(set(indices.tolist())) != len(indices):
            raise ValueError(f"partição {name} contém amostras duplicadas")
    if any(set(splits[left]) & set(splits[right]) for left, right in (("train", "validation"), ("validation", "test"), ("train", "test"))):
        raise ValueError("partições de treino, validação e teste se sobrepõem")
    return splits


def _models(seed: int) -> dict[str, tuple[ClassifierMixin, dict[str, list[Any]]]]:
    return {
        "logistic_regression": (
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
                ]
            ),
            {"model__C": [0.1, 1.0, 10.0], "model__class_weight": ["balanced", None]},
        ),
        "random_forest": (
            RandomForestClassifier(class_weight="balanced", random_state=seed, n_jobs=1),
            {
                "n_estimators": [100, 200],
                "max_depth": [4, 8, None],
                "min_samples_leaf": [2, 5],
            },
        ),
        "hist_gradient_boosting": (
            HistGradientBoostingClassifier(random_state=seed),
            {
                "learning_rate": [0.05, 0.1],
                "max_iter": [100, 150],
                "max_leaf_nodes": [7, 15],
                "l2_regularization": [0.0, 1.0],
            },
        ),
    }


def _metrics(targets: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    predictions = (probabilities >= 0.5).astype(np.int8)
    matrix = confusion_matrix(targets, predictions, labels=[0, 1])
    return {
        "threshold": 0.5,
        "accuracy": float(accuracy_score(targets, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(targets, predictions)),
        "precision": float(precision_score(targets, predictions, zero_division=0)),
        "recall": float(recall_score(targets, predictions, zero_division=0)),
        "f1": float(f1_score(targets, predictions, zero_division=0)),
        "average_precision": float(average_precision_score(targets, probabilities)),
        "confusion_matrix": matrix.tolist(),
    }


def train(
    features_path: Path,
    labels_path: Path,
    metadata_path: Path,
    output_dir: Path,
    tracking_uri: str,
    experiment_name: str,
    timezone: str,
    seed: int,
    search_iterations: int,
) -> dict[str, Any]:
    if not 1 <= search_iterations <= 12:
        raise ValueError("search_iterations deve estar entre 1 e 12")
    values, targets, timestamps, data_hash = _load_dataset(
        features_path, labels_path, metadata_path, timezone
    )
    splits = _split_indices(timestamps, timezone)
    if any(set(targets[indices]) != {0, 1} for indices in splits.values()):
        raise ValueError("cada partição temporal precisa conter as duas classes")

    train_indices = splits["train"]
    validation_indices = splits["validation"]
    test_indices = splits["test"]
    cv = TimeSeriesSplit(n_splits=3)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = output_dir / "mlflow-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    if mlflow.get_experiment_by_name(experiment_name) is None:
        client.create_experiment(experiment_name, artifact_location=artifact_dir.resolve().as_uri())
    mlflow.set_experiment(experiment_name)

    candidates: dict[str, dict[str, Any]] = {}
    specifications = _models(seed)
    model_search_budget = len(specifications) * search_iterations * cv.n_splits

    for name, (estimator, parameter_space) in specifications.items():
        sampled_parameters = list(
            ParameterSampler(parameter_space, n_iter=search_iterations, random_state=seed)
        )
        best_cv_score = -math.inf
        best_cv_train_score = -math.inf
        best_cv_std = 0.0
        best_parameters: dict[str, Any] = {}
        for parameters in sampled_parameters:
            train_scores: list[float] = []
            validation_scores: list[float] = []
            for fold_train, fold_validation in cv.split(values[train_indices]):
                model = clone(estimator).set_params(**parameters)
                actual_train = train_indices[fold_train]
                actual_validation = train_indices[fold_validation]
                model.fit(values[actual_train], targets[actual_train])
                train_probabilities = model.predict_proba(values[actual_train])[:, 1]
                validation_probabilities = model.predict_proba(values[actual_validation])[:, 1]
                train_scores.append(
                    float(average_precision_score(targets[actual_train], train_probabilities))
                )
                validation_scores.append(
                    float(average_precision_score(targets[actual_validation], validation_probabilities))
                )
            mean_validation = float(np.mean(validation_scores))
            if mean_validation > best_cv_score:
                best_cv_score = mean_validation
                best_cv_train_score = float(np.mean(train_scores))
                best_cv_std = float(np.std(validation_scores))
                best_parameters = parameters

        tuned = clone(estimator).set_params(**best_parameters)
        tuned.fit(values[train_indices], targets[train_indices])
        validation_metrics = _metrics(
            targets[validation_indices], tuned.predict_proba(values[validation_indices])[:, 1]
        )
        candidates[name] = {
            "best_parameters": best_parameters,
            "cv_mean_train_average_precision": best_cv_train_score,
            "cv_mean_validation_average_precision": best_cv_score,
            "cv_validation_average_precision_std": best_cv_std,
            "cv_generalization_gap": best_cv_train_score - best_cv_score,
            "validation": validation_metrics,
        }

    dummy = DummyClassifier(strategy="prior")
    dummy.fit(values[train_indices], targets[train_indices])
    dummy_validation = _metrics(
        targets[validation_indices], dummy.predict_proba(values[validation_indices])[:, 1]
    )
    train_validation = np.concatenate((train_indices, validation_indices))
    dummy_final = DummyClassifier(strategy="prior")
    dummy_final.fit(values[train_validation], targets[train_validation])
    dummy_test = _metrics(targets[test_indices], dummy_final.predict_proba(values[test_indices])[:, 1])
    candidates["dummy_prior"] = {"best_parameters": {}, "validation": dummy_validation}

    selected_model = max(
        specifications,
        key=lambda name: candidates[name]["validation"]["average_precision"],
    )
    selected_estimator, _ = specifications[selected_model]
    selected_final = clone(selected_estimator).set_params(
        **candidates[selected_model]["best_parameters"]
    )
    selected_final.fit(values[train_validation], targets[train_validation])
    selected_test = _metrics(
        targets[test_indices], selected_final.predict_proba(values[test_indices])[:, 1]
    )
    model_path = output_dir / "best_model.joblib"
    joblib.dump(selected_final, model_path)
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    split_counts = {name: int(len(indices)) for name, indices in splits.items()}
    first_local = timestamps[0].astimezone(ZoneInfo(timezone))
    origin = datetime.combine(first_local.date(), time.min, tzinfo=ZoneInfo(timezone))
    split_manifest = {
        "strategy": "chronological_local_days",
        "timezone": timezone,
        "durations_days": {"train": 8, "validation": 4, "test": 4},
        "start_local": origin.isoformat(),
        "train_end_local": (origin + timedelta(days=8)).isoformat(),
        "validation_end_local": (origin + timedelta(days=12)).isoformat(),
        "counts": split_counts,
        "data_sha256": data_hash,
    }
    report = {
        "task": "binary_classification",
        "target": TARGET_NAME,
        "sample_unit": "valid_reading_after_a_predecessor_reading",
        "timezone": timezone,
        "feature_names": list(FEATURE_NAMES),
        "threshold": 0.5,
        "selection_metric": "validation_average_precision",
        "selected_model": selected_model,
        "model_sha256": model_hash,
        "training_data_sha256": data_hash,
        "search": {
            "strategy": "random_parameter_sampling_with_time_series_cross_validation",
            "iterations_per_model": search_iterations,
            "folds_per_candidate": cv.n_splits,
            "total_candidate_fits": model_search_budget,
            "seed": seed,
        },
        "split_counts": split_counts,
        "candidates": candidates,
        "test_evaluation": {selected_model: selected_test, "dummy_prior": dummy_test},
        "synthetic_data_notice": (
            "metrics describe recognition of generated scenarios, not real-world leak detection"
        ),
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "split_manifest.json").write_text(
        json.dumps(split_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for name, result in candidates.items():
        with mlflow.start_run(run_name=name):
            mlflow.log_params(
                {
                    "model": name,
                    "target": TARGET_NAME,
                    "timezone": timezone,
                    "features": ",".join(FEATURE_NAMES),
                    "split_strategy": "chronological_8_4_4_days",
                    "search_iterations": search_iterations,
                    "seed": seed,
                    "data_sha256": data_hash,
                    "model_sha256": model_hash,
                    **{f"best_{key}": str(value) for key, value in result["best_parameters"].items()},
                }
            )
            split_results = {"validation": result["validation"]}
            if name == selected_model:
                split_results["test"] = selected_test
            elif name == "dummy_prior":
                split_results["test"] = dummy_test
            for split_name, metrics in split_results.items():
                for metric_name, value in metrics.items():
                    if metric_name != "confusion_matrix":
                        mlflow.log_metric(f"{split_name}_{metric_name}", float(value))
                mlflow.log_dict(
                    {"confusion_matrix": metrics["confusion_matrix"]},
                    f"{split_name}_confusion_matrix.json",
                )
            if name != "dummy_prior":
                mlflow.log_metric("cv_mean_train_average_precision", result["cv_mean_train_average_precision"])
                mlflow.log_metric(
                    "cv_mean_validation_average_precision",
                    result["cv_mean_validation_average_precision"],
                )
                mlflow.log_metric(
                    "cv_validation_average_precision_std",
                    result["cv_validation_average_precision_std"],
                )
                mlflow.log_metric("cv_generalization_gap", result["cv_generalization_gap"])
            if name == selected_model:
                mlflow.log_artifact(str(output_dir / "best_model.joblib"), artifact_path="model")
                mlflow.log_dict(report, "metrics.json")
                mlflow.log_dict(split_manifest, "split_manifest.json")

    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise RuntimeError("MLflow não criou o experimento esperado")
    report["mlflow_experiment_id"] = experiment.experiment_id
    (output_dir / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/ml/prepared/features.csv"))
    parser.add_argument("--labels", type=Path, default=Path("data/ml/prepared/labels.csv"))
    parser.add_argument("--metadata", type=Path, default=Path("data/ml/prepared/metadata.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/ml/training"))
    parser.add_argument(
        "--tracking-uri",
        default=f"sqlite:///{(Path('data/ml/mlflow.db').resolve()).as_posix()}",
    )
    parser.add_argument("--experiment-name", default="aquaflow-mock-anomaly-classification")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--search-iterations", type=int, default=4)
    args = parser.parse_args()
    train(
        args.features,
        args.labels,
        args.metadata,
        args.output_dir,
        args.tracking_uri,
        args.experiment_name,
        args.timezone,
        args.seed,
        args.search_iterations,
    )


if __name__ == "__main__":
    main()
