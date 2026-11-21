"""Prepare independently collected, reviewed 30-second telemetry for evaluation."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from feature_transforms import transform_window


def prepare(source: Path, output: Path, cutoff: datetime, timezone: str) -> dict:
    ZoneInfo(timezone)
    if cutoff.utcoffset() is None:
        raise ValueError("O corte de avaliação precisa incluir o fuso.")
    manifest = json.loads(source.with_suffix(source.suffix + ".json").read_text(encoding="utf-8"))
    if (
        manifest["sha256"] != sha256(source.read_bytes()).hexdigest()
        or manifest["stage"] != "reviewed_telemetry_export"
        or manifest["declared_origin"] not in {"physical", "simulated"}
        or manifest["expected_interval_seconds"] != 30
    ):
        raise ValueError("A exportação precisa ser íntegra e ter cadência de 30 segundos.")

    buckets = defaultdict(list)
    reading_ids = set()
    event_ids = set()
    with source.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["reading_id"] in reading_ids or row["event_id"] in event_ids:
                raise ValueError("IDs duplicados na exportação.")
            reading_ids.add(row["reading_id"])
            event_ids.add(row["event_id"])
            timestamp = datetime.fromisoformat(row["recorded_at"])
            if timestamp.utcoffset() is None or row["anomaly_label"] not in {"0", "1"}:
                raise ValueError("Timestamp ou rótulo inválido.")
            boundary = datetime.fromtimestamp(int(timestamp.timestamp()) // 300 * 300, UTC)
            volume = Decimal(row["cumulative_volume_liters"]) if row["cumulative_volume_liters"] else None
            if volume is not None and (not volume.is_finite() or volume < 0):
                volume = None
            buckets[boundary].append({
                **row,
                "recorded_at": timestamp,
                "cumulative_volume_liters": volume,
            })

    excluded = Counter()
    counts = Counter()
    samples = []
    window = timedelta(minutes=5)
    for boundary, readings in sorted(buckets.items()):
        readings.sort(key=lambda sample: sample["recorded_at"])
        previous = buckets.get(boundary - window, [])
        baseline = max(previous, key=lambda sample: sample["recorded_at"], default=None)
        if baseline is None or boundary - baseline["recorded_at"] > timedelta(seconds=45):
            excluded["baseline_missing"] += 1
            continue
        if boundary + window <= cutoff:
            partition = "development"
        elif baseline["recorded_at"] >= cutoff:
            partition = "evaluation"
        else:
            excluded["crosses_cutoff"] += 1
            continue
        if len({sample["anomaly_label"] for sample in readings}) != 1:
            excluded["mixed_labels"] += 1
            continue
        last = {
            **readings[-1],
            "window_start": boundary,
            "timezone": timezone,
            "expected_interval_seconds": 30,
        }
        features, reason = transform_window([baseline, *readings[:-1]], last, 300)
        if features is None:
            excluded[reason or "invalid_window"] += 1
            continue
        counts[partition] += 1
        samples.append({
            "partition": partition,
            "window_end": (boundary + window).isoformat(),
            "reading_ids": [sample["reading_id"] for sample in [baseline, *readings]],
            "event_ids": [sample["event_id"] for sample in [baseline, *readings]],
            "review_ids": [sample["review_id"] for sample in [baseline, *readings]],
            "anomaly_label": int(last["anomaly_label"]),
            "features": features,
        })

    output.mkdir(parents=True, exist_ok=True)
    data = output / "samples.jsonl"
    data.write_text("".join(json.dumps(sample) + "\n" for sample in samples), encoding="utf-8")
    result = {
        "preparation_version": 1,
        "source": manifest,
        "evaluation_cutoff": cutoff.astimezone(UTC).isoformat(),
        "timezone": timezone,
        "partition_counts": dict(counts),
        "exclusions": dict(excluded),
        "sha256": sha256(data.read_bytes()).hexdigest(),
    }
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--evaluation-cutoff", required=True, type=datetime.fromisoformat)
    parser.add_argument("--timezone", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.evaluation_cutoff, args.timezone)))
