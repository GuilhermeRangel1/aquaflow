"""Tests for the real-flow training dataset builder."""

import csv
import sys
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parents[1]
if str(ML) not in sys.path:
    sys.path.insert(0, str(ML))

import build_real_dataset as builder  # noqa: E402
import generate_mock_data as mock  # noqa: E402
import prepare_dataset  # noqa: E402

START = mock._start("2026-09-01T00:00:00-03:00")


def _write_real_csv(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    # rows: (scenario_label, flow_rate_liters_minute, quality)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["scenario_label", "flow_rate_liters_minute", "quality"])
        writer.writerows(rows)
    return path


def test_load_real_pools_groups_and_filters(tmp_path: Path) -> None:
    real = _write_real_csv(
        tmp_path / "real.csv",
        [
            ("normal", "0.1", "valid"),
            ("normal", "0.2", "valid"),
            ("continuous_flow", "0.5", "valid"),
            ("continuous_flow", "9.9", "invalid"),  # dropped: bad quality
            ("normal", "", "valid"),  # dropped: no flow
        ],
    )
    pools = builder.load_real_pools(real)
    assert pools["normal"] == [0.1, 0.2]
    assert pools["continuous_flow"] == [0.5]


def test_inject_replaces_flow_and_recomputes_volume() -> None:
    skeleton = [
        {"reading_present": "1", "scenario_label": "normal",
         "flow_rate_liters_minute": "0.010", "cumulative_volume_liters": "1000.010"},
        {"reading_present": "1", "scenario_label": "normal",
         "flow_rate_liters_minute": "0.012", "cumulative_volume_liters": "1000.070"},
    ]
    rows = builder.inject(skeleton, {"normal": [0.4]}, seed=1, interval_minutes=5)
    assert rows[0]["flow_rate_liters_minute"] == "0.400"
    assert rows[0]["cumulative_volume_liters"] == "1002.000"
    assert rows[1]["cumulative_volume_liters"] == "1004.000"


def test_inject_requires_pool_for_present_scenario() -> None:
    skeleton = [
        {"reading_present": "1", "scenario_label": "continuous_flow",
         "flow_rate_liters_minute": "0.2", "cumulative_volume_liters": "1000.2"},
    ]
    with pytest.raises(ValueError, match="cen"):
        builder.inject(skeleton, {"normal": [0.1]}, seed=1, interval_minutes=5)


def test_build_output_passes_prepare_analyze(tmp_path: Path) -> None:
    real = _write_real_csv(
        tmp_path / "real.csv",
        [
            *[("normal", f"0.0{n}", "valid") for n in range(1, 6)],
            *[("continuous_flow", f"0.{n}", "valid") for n in range(2, 7)],
            *[("night_consumption", f"0.{n}", "valid") for n in range(1, 6)],
        ],
    )
    output = tmp_path / "out" / "readings.csv"

    manifest = builder.build(
        real,
        output,
        seed=42,
        start=START,
        days=4,
        interval_minutes=60,
        timezone="America/Sao_Paulo",
    )

    assert output.exists()
    assert manifest["generated_rows"] > 0
    with output.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == mock.FIELDS

    # The built dataset must pass the same quality gate as the mock series.
    report = prepare_dataset.analyze(output, tmp_path / "eda")
    assert report["status"] == "passed"
    assert (tmp_path / "out" / "build_manifest.json").exists()
