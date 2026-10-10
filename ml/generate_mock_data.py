"""Generate reproducible, explicitly simulated water telemetry for ML experiments."""

import argparse
import csv
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

FIELDS = (
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
)


def _start(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--start requires a timezone")
    return parsed.astimezone(UTC)


def _flow(hour: int, rng: random.Random) -> float:
    if 6 <= hour < 9:
        base = 0.32
    elif 12 <= hour < 14:
        base = 0.18
    elif 18 <= hour < 22:
        base = 0.27
    else:
        base = 0.01
    return round(max(0, base + rng.uniform(-0.02, 0.02)), 3)


def generate(output: Path, *, seed: int, start: datetime, days: int, interval_minutes: int) -> None:
    if days < 4 or interval_minutes < 1 or 1440 % interval_minutes:
        raise ValueError("days must be >= 4 and interval_minutes must divide one day")
    rng = random.Random(seed)
    serial = "AF-ML-MOCK-001"
    cumulative = 1000.0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for slot in range(days * 1440 // interval_minutes):
            recorded_at = start + timedelta(minutes=slot * interval_minutes)
            day = slot * interval_minutes // 1440
            hour = recorded_at.hour
            scenario = "normal"
            present = True
            if day % 4 == 1 and 9 <= hour < 15:
                scenario = "continuous_flow"
            elif day % 4 == 2 and (hour >= 22 or hour < 6):
                scenario = "night_consumption"
            elif day % 4 == 3 and 12 <= hour < 14:
                scenario = "missing_reading"
                present = False
            flow = _flow(hour, rng)
            if scenario in {"continuous_flow", "night_consumption"}:
                flow = round(flow + 0.2, 3)
            cumulative = round(cumulative + flow * interval_minutes, 3)
            timestamp = recorded_at.isoformat().replace("+00:00", "Z")
            writer.writerow(
                {
                    "device_serial": serial,
                    "event_id": (
                        str(uuid5(NAMESPACE_URL, f"aquaflow:{seed}:{serial}:{timestamp}"))
                        if present
                        else ""
                    ),
                    "recorded_at": timestamp,
                    "cumulative_volume_liters": f"{cumulative:.3f}" if present else "",
                    "flow_rate_liters_minute": f"{flow:.3f}" if present else "",
                    "battery_percent": max(20, 95 - day // 2) if present else "",
                    "signal_dbm": -58 - day % 7 if present else "",
                    "firmware_version": "mock-ml-1" if present else "",
                    "reading_present": int(present),
                    "scenario_label": scenario,
                    "anomaly_label": int(scenario != "normal"),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/mock-ml/readings.csv"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", type=_start, default=_start("2026-09-01T00:00:00Z"))
    parser.add_argument("--days", type=int, default=16)
    parser.add_argument("--interval-minutes", type=int, default=5)
    args = parser.parse_args()
    generate(
        args.output,
        seed=args.seed,
        start=args.start,
        days=args.days,
        interval_minutes=args.interval_minutes,
    )
    print(f"Dados simulados gerados em {args.output}")


if __name__ == "__main__":
    main()
