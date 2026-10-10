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
from generate_mock_data import generate as generate_mock_data
from mlflow import MlflowClient
from prepare_dataset import prepare as prepare_dataset
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
        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None
            for timestamp in parsed_timestamps
        ):
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
    adjacent_split_pairs = (("train", "validation"), ("validation", "test"), ("train", "test"))
    if any(set(splits[left]) & set(splits[right]) for left, right in adjacent_split_pairs):
        raise ValueError("partições de treino, validação e teste se sobrepõem")
    return splits


def _generate_evaluation_profiles(
    timezone: str, seed: int, output_root: Path
) -> tuple[tuple[Path, Path, Path], tuple[Path, Path, Path]]:
    profile_inputs: dict[str, tuple[Path, Path, Path]] = {}
    for profile, profile_seed, start in (
        ("shifted", seed + 57, "2026-10-01T00:00:00-03:00"),
        ("stress", seed + 199, "2026-11-01T00:00:00-03:00"),
    ):
        profile_dir = output_root / "generalization" / profile
        raw_path = profile_dir / "raw_readings.csv"
        prepared_dir = profile_dir / "prepared"
        generate_mock_data(
            raw_path,
            seed=profile_seed,
            start=datetime.fromisoformat(start),
            days=16,
            interval_minutes=5,
            timezone=timezone,
            profile=profile,
        )
        prepare_dataset(raw_path, prepared_dir, timezone)
        profile_inputs[profile] = (
            prepared_dir / "features.csv",
            prepared_dir / "labels.csv",
            prepared_dir / "metadata.csv",
        )
    return profile_inputs["shifted"], profile_inputs["stress"]


def _models(seed: int) -> dict[str, tuple[ClassifierMixin, dict[str, list[Any]]]]:
    return {
        "logistic_regression": (
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
                ]
            ),
            {"model__C": [0.01, 0.1, 1.0], "model__class_weight": ["balanced", None]},
        ),
        "random_forest": (
            RandomForestClassifier(class_weight="balanced", random_state=seed, n_jobs=1),
            {
                "n_estimators": [100, 200],
                "max_depth": [2, 4, 6],
                "min_samples_leaf": [10, 20, 50],
                "max_features": ["sqrt", 0.7],
            },
        ),
        "hist_gradient_boosting": (
            HistGradientBoostingClassifier(random_state=seed),
            {
                "learning_rate": [0.03, 0.05],
                "max_iter": [30, 60],
                "max_leaf_nodes": [3, 5],
                "min_samples_leaf": [20, 40],
                "l2_regularization": [1.0, 10.0],
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
    generalization_validation_paths: tuple[Path, Path, Path] | None = None,
    stress_test_paths: tuple[Path, Path, Path] | None = None,
) -> dict[str, Any]:
    if not 1 <= search_iterations <= 12:
        raise ValueError("search_iterations deve estar entre 1 e 12")
    values, targets, timestamps, data_hash = _load_dataset(
        features_path, labels_path, metadata_path, timezone
    )
    if (generalization_validation_paths is None) != (stress_test_paths is None):
        raise ValueError("generalization validation e stress test devem ser informados juntos")
    shifted_values: np.ndarray | None = None
    shifted_targets: np.ndarray | None = None
    shifted_hash: str | None = None
    stress_values: np.ndarray | None = None
    stress_targets: np.ndarray | None = None
    stress_hash: str | None = None
    if generalization_validation_paths and stress_test_paths:
        shifted_values, shifted_targets, _, shifted_hash = _load_dataset(
            *generalization_validation_paths, timezone
        )
        stress_values, stress_targets, _, stress_hash = _load_dataset(
            *stress_test_paths, timezone
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
                    float(
                        average_precision_score(
                            targets[actual_validation], validation_probabilities
                        )
                    )
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
        generalization_metrics = (
            _metrics(shifted_targets, tuned.predict_proba(shifted_values)[:, 1])
            if shifted_values is not None and shifted_targets is not None
            else None
        )
        candidates[name] = {
            "best_parameters": best_parameters,
            "cv_mean_train_average_precision": best_cv_train_score,
            "cv_mean_validation_average_precision": best_cv_score,
            "cv_validation_average_precision_std": best_cv_std,
            "cv_generalization_gap": best_cv_train_score - best_cv_score,
            "validation": validation_metrics,
            "generalization_validation": generalization_metrics,
        }

    dummy = DummyClassifier(strategy="prior")
    dummy.fit(values[train_indices], targets[train_indices])
    dummy_validation = _metrics(
        targets[validation_indices], dummy.predict_proba(values[validation_indices])[:, 1]
    )
    train_validation = np.concatenate((train_indices, validation_indices))
    candidates["dummy_prior"] = {"best_parameters": {}, "validation": dummy_validation}
    candidates["dummy_prior"]["generalization_validation"] = (
        _metrics(shifted_targets, dummy.predict_proba(shifted_values)[:, 1])
        if shifted_values is not None and shifted_targets is not None
        else None
    )

    def selection_score(name: str) -> float:
        in_domain_score = candidates[name]["validation"]["average_precision"]
        shifted_result = candidates[name]["generalization_validation"]
        if shifted_result is None:
            return in_domain_score
        return float(
            np.mean(
                [
                    in_domain_score,
                    shifted_result["average_precision"],
                ]
            )
        )

    selected_model = max(
        specifications,
        key=selection_score,
    )
    selected_estimator, _ = specifications[selected_model]
    selected_final = clone(selected_estimator).set_params(
        **candidates[selected_model]["best_parameters"]
    )
    final_train_values = values[train_validation]
    final_train_targets = targets[train_validation]
    if shifted_values is not None and shifted_targets is not None:
        final_train_values = np.concatenate((final_train_values, shifted_values))
        final_train_targets = np.concatenate((final_train_targets, shifted_targets))
    final_training_fingerprint = hashlib.sha256(data_hash.encode("ascii"))
    if shifted_hash is not None:
        final_training_fingerprint.update(shifted_hash.encode("ascii"))
    final_training_data_hash = final_training_fingerprint.hexdigest()
    dummy_final = DummyClassifier(strategy="prior")
    dummy_final.fit(final_train_values, final_train_targets)
    dummy_test = _metrics(
        targets[test_indices], dummy_final.predict_proba(values[test_indices])[:, 1]
    )
    selected_final.fit(final_train_values, final_train_targets)
    selected_test = _metrics(
        targets[test_indices], selected_final.predict_proba(values[test_indices])[:, 1]
    )
    stress_test_metrics = (
        _metrics(stress_targets, selected_final.predict_proba(stress_values)[:, 1])
        if stress_values is not None and stress_targets is not None
        else None
    )
    selected_shifted_metrics = candidates[selected_model]["generalization_validation"]
    validation_domain_gap = (
        abs(
            candidates[selected_model]["validation"]["average_precision"]
            - selected_shifted_metrics["average_precision"]
        )
        if selected_shifted_metrics is not None
        else None
    )
    cv_gap = candidates[selected_model]["cv_generalization_gap"]
    cv_std = candidates[selected_model]["cv_validation_average_precision_std"]
    stress_average_precision = (
        stress_test_metrics["average_precision"] if stress_test_metrics else None
    )
    temporal_cv_assessment = _overfitting_assessment(cv_gap, cv_std)
    domain_shift_assessment = (
        "sensitivity_detected"
        if validation_domain_gap is not None and validation_domain_gap > 0.15
        else "no_large_validation_gap_detected"
        if validation_domain_gap is not None
        else "not_evaluated"
    )
    if stress_average_precision is not None and stress_average_precision < 0.7:
        domain_shift_assessment = "sensitivity_detected"
    model_path = output_dir / "best_model.joblib"
    joblib.dump(selected_final, model_path)
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    split_counts = {name: len(indices) for name, indices in splits.items()}
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
        "explanation_reference": {
            name: float(value)
            for name, value in zip(
                FEATURE_NAMES,
                np.median(values[train_indices], axis=0),
                strict=True,
            )
        },
        "threshold": 0.5,
        "selection_metric": (
            "mean_average_precision_across_temporal_and_shifted_validation"
            if shifted_values is not None
            else "validation_average_precision"
        ),
        "selection_scores": {name: selection_score(name) for name in candidates},
        "selected_model": selected_model,
        "model_sha256": model_hash,
        "training_data_sha256": data_hash,
        "final_training_data_sha256": final_training_data_hash,
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
        "generalization_validation": (
            {
                "profile": "shifted",
                "data_sha256": shifted_hash,
                "sample_count": len(shifted_targets),
                "candidates": {
                    name: result["generalization_validation"]
                    for name, result in candidates.items()
                },
            }
            if shifted_values is not None and shifted_targets is not None
            else None
        ),
        "stress_test_evaluation": (
            {
                "profile": "stress",
                "data_sha256": stress_hash,
                "sample_count": len(stress_targets),
                "selected_model": stress_test_metrics,
                "dummy_prior": _metrics(
                    stress_targets,
                    dummy_final.predict_proba(stress_values)[:, 1],
                ),
            }
            if stress_values is not None
            and stress_targets is not None
            and stress_test_metrics is not None
            else None
        ),
        "overfitting_diagnostics": {
            "cv_generalization_gap": cv_gap,
            "cv_validation_average_precision_std": cv_std,
            "temporal_cv_assessment": temporal_cv_assessment,
            "validation_domain_gap": validation_domain_gap,
            "stress_test_average_precision": stress_average_precision,
            "domain_shift_assessment": domain_shift_assessment,
            "assessment_thresholds": {
                "cv_gap_warning": 0.1,
                "cv_validation_std_warning": 0.1,
                "validation_domain_gap_warning": 0.15,
                "stress_test_average_precision_warning_below": 0.7,
            },
            "limits": "Heuristic diagnostics for investigation; synthetic profiles do not establish real-world generalization.",
        },
        "final_training_sample_count": len(final_train_targets),
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
    report_markdown_path = output_dir / "training_report.md"
    report_markdown_path.write_text(_training_report_markdown(report), encoding="utf-8")

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
                    "final_training_data_sha256": final_training_data_hash,
                    **({"model_sha256": model_hash} if name == selected_model else {}),
                    **{
                        f"best_{key}": str(value)
                        for key, value in result["best_parameters"].items()
                    },
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
                mlflow.log_metric(
                    "cv_mean_train_average_precision",
                    result["cv_mean_train_average_precision"],
                )
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
                mlflow.log_artifact(str(report_markdown_path))

    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise RuntimeError("MLflow não criou o experimento esperado")
    report["mlflow_experiment_id"] = experiment.experiment_id
    (output_dir / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return report


def _overfitting_assessment(generalization_gap: float, validation_std: float) -> str:
    if generalization_gap > 0.1 or validation_std > 0.1:
        return "possible_overfitting_or_instability"
    return "no_large_gap_detected_in_temporal_cv"


def _training_report_markdown(report: dict[str, Any]) -> str:
    selected = report["selected_model"]
    diagnostics = report["overfitting_diagnostics"]

    def format_metric(value: float | None) -> str:
        return f"{value:.3f}" if value is not None else "—"

    lines = [
        "# Relatório do experimento de classificação de anomalias",
        "",
        f"Modelo selecionado: **{selected}**.",
        "",
        f"- Amostras usadas no ajuste final: {report['final_training_sample_count']}.",
        f"- Partições temporais originais: {report['split_counts']}.",
        f"- Busca de hiperparâmetros: {report['search']['total_candidate_fits']} ajustes; seed {report['search']['seed']}.",
        f"- Hash dos dados da série principal: `{report['training_data_sha256']}`.",
        f"- Hash combinado dos dados usados no ajuste final: `{report['final_training_data_sha256']}`.",
        f"- Hiperparâmetros escolhidos: `{report['candidates'][selected]['best_parameters']}`.",
        "",
        "## Como foi avaliado",
        "",
        (
            "A seleção usa average precision média entre a validação temporal e a validação com perfil deslocado. "
            "O perfil de estresse só é avaliado depois da seleção e não participa do ajuste dos hiperparâmetros."
        ),
        "",
        "| Candidato | AP temporal | AP perfil deslocado | AP média de seleção | Gap treino/CV | Variação CV |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, result in report["candidates"].items():
        cv_gap = result.get("cv_generalization_gap")
        cv_std = result.get("cv_validation_average_precision_std")
        shifted = result.get("generalization_validation")
        lines.append(
            f"| {name} | {result['validation']['average_precision']:.3f} | "
            f"{format_metric(shifted['average_precision'] if shifted else None)} | "
            f"{report['selection_scores'][name]:.3f} | "
            f"{format_metric(cv_gap)} | {format_metric(cv_std)} |"
        )
    lines.extend(
        [
            "",
            "## Diagnóstico",
            "",
            f"- Avaliação temporal: `{diagnostics['temporal_cv_assessment']}`.",
            f"- Diferença de AP entre validação temporal e perfil deslocado: {format_metric(diagnostics['validation_domain_gap'])}.",
            f"- AP no perfil de estresse independente: {format_metric(diagnostics['stress_test_average_precision'])}.",
            "- Os limiares do diagnóstico são sinais de investigação, não critérios de aprovação estatística.",
            "",
            "## Resultado no teste",
            "",
        ]
    )
    test_metrics = report["test_evaluation"][selected]
    lines.extend(
        [
            (
                f"- Série principal: AP {test_metrics['average_precision']:.3f}, precisão {test_metrics['precision']:.3f}, "
                f"recall {test_metrics['recall']:.3f}, F1 {test_metrics['f1']:.3f}."
            ),
            f"- Matriz de confusão da série principal: `{test_metrics['confusion_matrix']}` (linhas: real 0/1; colunas: previsto 0/1).",
        ]
    )
    stress_metrics = report["stress_test_evaluation"]
    if stress_metrics:
        metrics = stress_metrics["selected_model"]
        lines.extend(
            [
                (
                    f"- Perfil de estresse: AP {metrics['average_precision']:.3f}, precisão {metrics['precision']:.3f}, "
                    f"recall {metrics['recall']:.3f}, F1 {metrics['f1']:.3f}."
                ),
                f"- Matriz de confusão do perfil de estresse: `{metrics['confusion_matrix']}` (linhas: real 0/1; colunas: previsto 0/1).",
            ]
        )
    lines.extend(
        [
            "",
            "## Limitações",
            "",
            (
                "Todos os perfis são sintéticos e definidos pelo gerador do projeto. O teste de estresse mede sensibilidade "
                "a mudanças construídas de rotina, ruído e intensidade; não demonstra desempenho em consumo real nem "
                "confirma vazamentos."
            ),
            "",
        ]
    )
    return "\n".join(lines)


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
    parser.add_argument("--generalization-validation-features", type=Path)
    parser.add_argument("--generalization-validation-labels", type=Path)
    parser.add_argument("--generalization-validation-metadata", type=Path)
    parser.add_argument("--stress-test-features", type=Path)
    parser.add_argument("--stress-test-labels", type=Path)
    parser.add_argument("--stress-test-metadata", type=Path)
    args = parser.parse_args()
    shifted_paths = (
        args.generalization_validation_features,
        args.generalization_validation_labels,
        args.generalization_validation_metadata,
    )
    stress_paths = (
        args.stress_test_features,
        args.stress_test_labels,
        args.stress_test_metadata,
    )
    if any(path is not None for path in shifted_paths) and not all(
        path is not None for path in shifted_paths
    ):
        parser.error("informe os três arquivos de generalization validation juntos")
    if any(path is not None for path in stress_paths) and not all(
        path is not None for path in stress_paths
    ):
        parser.error("informe os três arquivos de stress test juntos")
    shifted_input = tuple(shifted_paths) if all(path is not None for path in shifted_paths) else None
    stress_input = tuple(stress_paths) if all(path is not None for path in stress_paths) else None
    if shifted_input is None and stress_input is None:
        shifted_input, stress_input = _generate_evaluation_profiles(
            args.timezone, args.seed, args.output_dir.parent
        )
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
        shifted_input,
        stress_input,
    )


if __name__ == "__main__":
    main()
