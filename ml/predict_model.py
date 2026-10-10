"""Run offline predictions for a dataset prepared by prepare_dataset.py."""

import argparse
import csv
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import joblib
import numpy as np
from feature_transforms import FEATURE_NAMES

METADATA_NAMES = ("event_id", "recorded_at", "device_serial")


def _read_csv(path: Path, expected_columns: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != expected_columns:
            raise ValueError(f"schema inválido em {path.name}")
        return list(reader)


def predict(
    features_path: Path,
    metadata_path: Path,
    preparation_manifest_path: Path,
    model_path: Path,
    training_report_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifest = json.loads(preparation_manifest_path.read_text(encoding="utf-8"))
    training_report = json.loads(training_report_path.read_text(encoding="utf-8"))
    timezone = training_report.get("timezone")
    if not isinstance(timezone, str) or manifest.get("timezone") != timezone:
        raise ValueError("o fuso da preparação deve corresponder ao fuso do treinamento")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"fuso horário IANA inválido: {timezone}") from error
    if training_report.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("o modelo foi treinado com outro conjunto de features")

    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if training_report.get("model_sha256") != model_hash:
        raise ValueError("o artefato do modelo não corresponde ao relatório de treinamento")

    features = _read_csv(features_path, FEATURE_NAMES)
    metadata = _read_csv(metadata_path, METADATA_NAMES)
    if not features or len(features) != len(metadata):
        raise ValueError("features e metadata devem conter a mesma quantidade de amostras")
    event_ids = [row["event_id"] for row in metadata]
    if any(not event_id for event_id in event_ids) or len(set(event_ids)) != len(event_ids):
        raise ValueError("event_id deve ser preenchido e único")
    if manifest.get("prepared_readings") != len(features):
        raise ValueError("quantidade de amostras difere do manifesto de preparação")

    try:
        timestamps = [
            datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00")) for row in metadata
        ]
        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None for timestamp in timestamps
        ):
            raise ValueError("recorded_at deve incluir fuso horário")
        timestamps_utc = [timestamp.astimezone(UTC) for timestamp in timestamps]
        values = np.asarray(
            [[float(row[name]) for name in FEATURE_NAMES] for row in features], dtype=np.float64
        )
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f"dataset de inferência inválido: {error}") from error
    if not np.isfinite(values).all():
        raise ValueError("features devem conter somente valores finitos")
    if timestamps_utc != sorted(timestamps_utc) or len(set(timestamps_utc)) != len(timestamps_utc):
        raise ValueError("metadata deve estar em ordem cronológica sem timestamps duplicados")

    model = joblib.load(model_path)
    probabilities = model.predict_proba(values)[:, 1]
    threshold = float(training_report.get("threshold", 0.5))
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("limiar do modelo deve estar entre 0 e 1")
    if not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("modelo produziu probabilidades inválidas")
    predictions = (probabilities >= threshold).astype(np.int8)
    reference = training_report.get("explanation_reference")
    if not isinstance(reference, dict) or set(reference) != set(FEATURE_NAMES):
        raise ValueError("relatório de treinamento não contém referência para explicações")
    reference_values = np.asarray([float(reference[name]) for name in FEATURE_NAMES])
    explanation_effects = []
    for feature_index in range(len(FEATURE_NAMES)):
        counterfactual = values.copy()
        counterfactual[:, feature_index] = reference_values[feature_index]
        counterfactual_probabilities = model.predict_proba(counterfactual)[:, 1]
        explanation_effects.append(probabilities - counterfactual_probabilities)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / "predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=(
                "event_id",
                "recorded_at",
                "predicted_anomaly",
                "anomaly_probability",
                "model_version",
                "feature_effects_json",
            ),
        )
        writer.writeheader()
        for row_index, (row, prediction, probability) in enumerate(
            zip(metadata, predictions, probabilities, strict=True)
        ):
            effects = {
                name: round(float(explanation_effects[index][row_index]), 6)
                for index, name in enumerate(FEATURE_NAMES)
            }
            writer.writerow(
                {
                    "event_id": row["event_id"],
                    "recorded_at": row["recorded_at"],
                    "predicted_anomaly": int(prediction),
                    "anomaly_probability": f"{float(probability):.8f}",
                    "model_version": model_hash,
                    "feature_effects_json": json.dumps(effects, sort_keys=True),
                }
            )

    input_hash = hashlib.sha256()
    for path in (features_path, metadata_path, preparation_manifest_path):
        input_hash.update(path.read_bytes())
    result = {
        "status": "offline_simulated_inference",
        "selected_model": training_report["selected_model"],
        "model_version": model_hash,
        "training_data_sha256": training_report["training_data_sha256"],
        "inference_data_sha256": input_hash.hexdigest(),
        "timezone": timezone,
        "threshold": threshold,
        "prediction_count": len(features),
        "predicted_anomalies": int(np.sum(predictions)),
        "prediction_file": predictions_path.name,
        "limitation": (
            "predictions describe generated scenarios and are not validated on real telemetry"
        ),
    }
    (output_dir / "prediction_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features", type=Path, default=Path("data/ml/inference/prepared/features.csv")
    )
    parser.add_argument(
        "--metadata", type=Path, default=Path("data/ml/inference/prepared/metadata.csv")
    )
    parser.add_argument(
        "--preparation-manifest",
        type=Path,
        default=Path("data/ml/inference/prepared/preparation_manifest.json"),
    )
    parser.add_argument("--model", type=Path, default=Path("data/ml/training/best_model.joblib"))
    parser.add_argument(
        "--training-report", type=Path, default=Path("data/ml/training/metrics.json")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/ml/predictions"))
    args = parser.parse_args()
    predict(
        args.features,
        args.metadata,
        args.preparation_manifest,
        args.model,
        args.training_report,
        args.output_dir,
    )


if __name__ == "__main__":
    main()
