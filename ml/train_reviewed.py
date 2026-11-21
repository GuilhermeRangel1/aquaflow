"""Train and evaluate a candidate from two separately prepared collections."""

import argparse
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import joblib
import mlflow
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from feature_transforms import FEATURE_NAMES
from train_model import _metrics


def load_partition(directory: Path, partition: str) -> tuple[dict, list[dict]]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    data = (directory / "samples.jsonl").read_bytes()
    if manifest["preparation_version"] != 1 or sha256(data).hexdigest() != manifest["sha256"]:
        raise ValueError("Dataset preparado inválido ou alterado.")
    samples = [json.loads(line) for line in data.splitlines()]
    return manifest, [sample for sample in samples if sample["partition"] == partition]


def fit_candidate(development: Path, evaluation: Path, output: Path, tracking_uri: str) -> dict:
    train_manifest, train = load_partition(development, "development")
    test_manifest, test = load_partition(evaluation, "evaluation")
    train_source = train_manifest["source"]
    test_source = test_manifest["source"]
    if train_source["declared_origin"] != test_source["declared_origin"]:
        raise ValueError("Treino e avaliação precisam ter a mesma origem declarada.")
    if datetime.fromisoformat(train_source["end_exclusive"]) > datetime.fromisoformat(
        test_source["start"]
    ):
        raise ValueError("Reserve uma coleta de avaliação posterior, em intervalo separado.")
    train_ids = {value for sample in train for value in sample["reading_ids"]}
    test_ids = {value for sample in test for value in sample["reading_ids"]}
    if train_ids & test_ids:
        raise ValueError("Treino e avaliação compartilham leituras.")

    def arrays(samples: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        targets = np.asarray([sample["anomaly_label"] for sample in samples])
        if set(targets) != {0, 1}:
            raise ValueError("Cada partição precisa conter exemplos normais e anômalos.")
        values = np.asarray([[sample["features"][name] for name in FEATURE_NAMES] for sample in samples])
        if not np.isfinite(values).all():
            raise ValueError("Dataset contém valores não finitos.")
        return values, targets

    train_values, train_targets = arrays(train)
    test_values, test_targets = arrays(test)
    minimum_per_class = 25
    class_counts = {
        name: {str(label): int(np.count_nonzero(targets == label)) for label in (0, 1)}
        for name, targets in (("development", train_targets), ("evaluation", test_targets))
    }
    if any(count < minimum_per_class for counts in class_counts.values() for count in counts.values()):
        raise ValueError(f"Cada partição precisa de ao menos {minimum_per_class} exemplos por classe.")
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=42))
    model.fit(train_values, train_targets)
    metrics = _metrics(test_targets, model.predict_proba(test_values)[:, 1])
    output.mkdir(parents=True, exist_ok=False)
    model_path = output / "best_model.joblib"
    joblib.dump(model, model_path)
    report = {
        "task": "binary_classification",
        "feature_names": list(FEATURE_NAMES),
        "selected_model": "logistic_regression",
        "model_sha256": sha256(model_path.read_bytes()).hexdigest(),
        "status": "evaluated_candidate",
        "threshold": 0.5,
        "explanation_reference": {
            name: float(np.median([sample["features"][name] for sample in train]))
            for name in FEATURE_NAMES
        },
        "candidates": {
            "logistic_regression": {
                "validation": metrics,
                "train": _metrics(train_targets, model.predict_proba(train_values)[:, 1]),
            }
        },
        "test_evaluation": {"logistic_regression": metrics},
        "stress_test_evaluation": {"selected_model": metrics},
        "development": train_manifest,
        "evaluation": test_manifest,
        "partition_counts": {"development": len(train), "evaluation": len(test)},
        "class_counts": class_counts,
        "approval": {
            "minimum_examples_per_class": minimum_per_class,
            "minimum_average_precision": 0.8,
            "minimum_recall": 0.8,
            "passed": metrics["average_precision"] >= 0.8 and metrics["recall"] >= 0.8,
        },
        "test_metrics": metrics,
    }
    report_path = output / "metrics.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("aquaflow-reviewed-telemetry")
    with mlflow.start_run():
        mlflow.log_params({
            "origin": train_source["declared_origin"],
            "development_sha256": train_manifest["sha256"],
            "evaluation_sha256": test_manifest["sha256"],
            **report["partition_counts"],
        })
        mlflow.log_metrics({name: float(value) for name, value in metrics.items() if isinstance(value, (int, float))})
        mlflow.log_artifact(str(report_path))
        mlflow.log_artifact(str(model_path))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("development", type=Path)
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tracking-uri", required=True)
    args = parser.parse_args()
    fit_candidate(args.development, args.evaluation, args.output, args.tracking_uri)
