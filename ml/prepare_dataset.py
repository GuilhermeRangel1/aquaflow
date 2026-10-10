"""Validate, summarize, and prepare the generated mock telemetry for ML work."""

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "device_serial",
    "event_id",
    "recorded_at",
    "cumulative_volume_liters",
    "flow_rate_liters_minute",
    "battery_percent",
    "signal_dbm",
    "firmware_version",
    "reading_present",
    "scenario_label",
    "anomaly_label",
}
SCENARIOS = {"normal", "continuous_flow", "night_consumption", "missing_reading"}
MEASUREMENTS = (
    "cumulative_volume_liters",
    "flow_rate_liters_minute",
    "battery_percent",
    "signal_dbm",
)
FEATURE_FIELDS = (
    "event_id",
    "recorded_at",
    "device_serial",
    "cumulative_volume_liters",
    "flow_rate_liters_minute",
    "battery_percent",
    "signal_dbm",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
)
LABEL_FIELDS = ("event_id", "scenario_label", "anomaly_label")


def _parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp sem fuso horário")
    return result.astimezone(UTC)


def _number(row: dict[str, str], field: str) -> float:
    value = float(row[field])
    if not math.isfinite(value):
        raise ValueError(f"{field} não é finito")
    return value


def _validate_row(row: dict[str, str], row_number: int) -> tuple[dict[str, Any] | None, str | None]:
    try:
        timestamp = _parse_time(row["recorded_at"])
        present = int(row["reading_present"])
        anomaly = int(row["anomaly_label"])
        scenario = row["scenario_label"]
        if present not in {0, 1} or anomaly not in {0, 1}:
            raise ValueError("indicador deve ser 0 ou 1")
        if scenario not in SCENARIOS:
            raise ValueError("cenário desconhecido")
        if anomaly != int(scenario != "normal"):
            raise ValueError("rótulo de anomalia não corresponde ao cenário")
        if not row["device_serial"]:
            raise ValueError("device_serial vazio")

        measurements = {field: row[field] for field in MEASUREMENTS}
        if not present:
            if row["event_id"] or any(value for value in measurements.values()):
                raise ValueError("lacuna contém identificador ou telemetria")
            return (
                {
                    "row_number": row_number,
                    "recorded_at": timestamp,
                    "reading_present": 0,
                    "scenario_label": scenario,
                    "anomaly_label": anomaly,
                },
                None,
            )

        from uuid import UUID

        event_id = str(UUID(row["event_id"]))
        values = {field: _number(row, field) for field in MEASUREMENTS}
        if any(values[field] < 0 for field in MEASUREMENTS[:3]):
            raise ValueError("volume, vazão e bateria não podem ser negativos")
        if values["battery_percent"] > 100:
            raise ValueError("bateria acima de 100%")
        if not -150 <= values["signal_dbm"] <= 0:
            raise ValueError("signal_dbm fora do intervalo plausível [-150, 0]")
        if not row["firmware_version"]:
            raise ValueError("firmware_version vazio")
        return (
            {
                "row_number": row_number,
                "event_id": event_id,
                "recorded_at": timestamp,
                "device_serial": row["device_serial"],
                **values,
                "reading_present": 1,
                "scenario_label": scenario,
                "anomaly_label": anomaly,
            },
            None,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return None, f"linha {row_number}: {error}"


def _describe(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.fmean(values), 6),
        "max": max(values),
    }


def analyze(input_path: Path, output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    scenario_counts: Counter[str] = Counter()
    with input_path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing_fields = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing_fields:
            raise ValueError(f"colunas obrigatórias ausentes: {sorted(missing_fields)}")
        for row_number, row in enumerate(reader, start=2):
            scenario_counts[row.get("scenario_label", "")] += 1
            record, error = _validate_row(row, row_number)
            if error:
                errors.append(error)
            elif record is not None:
                records.append(record)

    ordered = sorted(records, key=lambda record: record["recorded_at"])
    timestamps = [record["recorded_at"] for record in records]
    event_ids = [record["event_id"] for record in records if record["reading_present"]]
    duplicate_timestamps = len(timestamps) - len(set(timestamps))
    duplicate_event_ids = len(event_ids) - len(set(event_ids))
    if duplicate_timestamps:
        errors.append(f"{duplicate_timestamps} timestamps duplicados")
    if duplicate_event_ids:
        errors.append(f"{duplicate_event_ids} event_id duplicados")
    if records != ordered:
        errors.append("timestamps fora de ordem crescente")
    intervals = [
        int((right - left).total_seconds() // 60)
        for left, right in zip(timestamps, timestamps[1:], strict=False)
        if right > left
    ]
    expected_interval = Counter(intervals).most_common(1)[0][0] if intervals else None
    time_gaps = (
        sum(interval > expected_interval for interval in intervals) if expected_interval else 0
    )
    present = [record for record in records if record["reading_present"]]
    if not records:
        errors.append("dataset sem linhas")
    elif not present:
        errors.append("dataset sem leituras válidas")
    missing_slots = sum(1 for record in records if not record["reading_present"])
    expected_slots = len(records)

    checks = {
        "required_columns_present": True,
        "timestamps_unique": duplicate_timestamps == 0,
        "event_ids_unique": duplicate_event_ids == 0,
        "timestamps_ordered": records == ordered,
        "rows_valid": not errors,
    }
    report: dict[str, Any] = {
        "source_file": input_path.name,
        "status": "passed" if not errors else "failed",
        "checks": checks,
        "row_counts": {
            "expected_slots": expected_slots,
            "readings_present": len(present),
            "missing_readings": missing_slots,
            "coverage_ratio": round(len(present) / expected_slots, 6) if expected_slots else 0,
        },
        "time_range_utc": {
            "start": timestamps[0].isoformat().replace("+00:00", "Z") if timestamps else None,
            "end": timestamps[-1].isoformat().replace("+00:00", "Z") if timestamps else None,
            "expected_interval_minutes": expected_interval,
            "gaps_between_rows": time_gaps,
        },
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "duplicate_timestamps": duplicate_timestamps,
        "duplicate_event_ids": duplicate_event_ids,
        "measurements": {
            field: _describe([record[field] for record in present]) for field in MEASUREMENTS
        },
        "errors": errors,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "eda_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if errors:
        raise ValueError(f"qualidade dos dados reprovada; consulte {report_path}")
    return report


def prepare(input_path: Path, output_dir: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    with input_path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if REQUIRED_FIELDS - set(reader.fieldnames or []):
            raise ValueError("schema de entrada inválido; execute a análise primeiro")
        for row_number, row in enumerate(reader, start=2):
            record, error = _validate_row(row, row_number)
            if error:
                raise ValueError(f"dados inválidos; execute a análise primeiro: {error}")
            if record is not None and record["reading_present"]:
                records.append(record)

    output_dir.mkdir(parents=True, exist_ok=True)
    features_path = output_dir / "features.csv"
    labels_path = output_dir / "labels.csv"
    with features_path.open("w", newline="", encoding="utf-8") as features_file:
        writer = csv.DictWriter(features_file, fieldnames=FEATURE_FIELDS)
        writer.writeheader()
        for record in records:
            timestamp: datetime = record["recorded_at"]
            hour = timestamp.hour + timestamp.minute / 60
            weekday = timestamp.weekday()
            writer.writerow(
                {
                    "event_id": record["event_id"],
                    "recorded_at": timestamp.isoformat().replace("+00:00", "Z"),
                    "device_serial": record["device_serial"],
                    **{field: record[field] for field in MEASUREMENTS},
                    "hour_sin": round(math.sin(2 * math.pi * hour / 24), 8),
                    "hour_cos": round(math.cos(2 * math.pi * hour / 24), 8),
                    "weekday_sin": round(math.sin(2 * math.pi * weekday / 7), 8),
                    "weekday_cos": round(math.cos(2 * math.pi * weekday / 7), 8),
                }
            )
    with labels_path.open("w", newline="", encoding="utf-8") as labels_file:
        writer = csv.DictWriter(labels_file, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        writer.writerows(
            {
                "event_id": record["event_id"],
                "scenario_label": record["scenario_label"],
                "anomaly_label": record["anomaly_label"],
            }
            for record in records
        )

    manifest = {
        "source_file": input_path.name,
        "prepared_readings": len(records),
        "missing_rows_policy": "missing slots are excluded from feature/label tables, not imputed",
        "label_policy": "scenario and anomaly labels are written separately from model features",
        "time_features": "hour and weekday encoded with sine/cosine cycles in UTC",
        "scaling_policy": (
            "not fitted yet; choose task and split by time before fitting data-dependent transforms"
        ),
        "feature_file": features_path.name,
        "label_file": labels_path.name,
    }
    manifest_path = output_dir / "preparation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("analyze", "prepare"))
    parser.add_argument("--input", type=Path, default=Path("data/mock-ml/readings.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/ml"))
    args = parser.parse_args()
    result = (
        analyze(args.input, args.output_dir)
        if args.action == "analyze"
        else prepare(args.input, args.output_dir)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
