"""Monta uma série híbrida a partir de coletas de bancada ou dados rotulados.

Reusa ``generate_mock_data`` para o esqueleto (dias, cadência e agenda de
cenários). A fonte de bancada fornece as medianas positivas por corrida que
calibram os eventos simulados; a fonte ``--real`` fornece pools de vazões
rotuladas pelo cenário. Horário, cenário, ``event_id`` e metadados de
dispositivo continuam vindos do esqueleto. Isto não decide vazamento: os
rótulos e a rotina doméstica da série calibrada são simulados.

Limitações registradas: a vazão é amostrada de forma independente por intervalo
a partir do pool real de cada cenário, então a autocorrelação temporal das
corridas reais não é preservada; bateria e sinal continuam sintéticos e não são
features. As métricas resultantes não comprovam detecção de vazamento real.
"""

import argparse
import csv
import json
import math
import random
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

import generate_mock_data as mock

VALID_QUALITY = {"valid"}
BASE_VOLUME_LITERS = 1000.0
DEFAULT_CALIBRATION = Path(__file__).parent / "collection" / "bench-calibration-v1.json"


def load_bench_rates(
    directory: Path,
    exclude_flows: list[float],
    excluded_measurements: dict[str, list[int]] | None = None,
) -> dict[str, float]:
    """Use configured median positive readings from each real bench run."""
    rates = {}
    excluded_measurements = excluded_measurements or {}
    for path in sorted(directory.glob("bench_features_*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as source:
            rows = list(csv.DictReader(source))
        excluded_rows = set(excluded_measurements.get(path.name, []))
        values = []
        for row in rows:
            if excluded_rows and int(row["medicao"]) in excluded_rows:
                continue
            values.append(float(row["flow_rate_liters_minute"]))
        valid = [
            value for value in values
            if math.isfinite(value) and value > 0 and value not in exclude_flows
        ]
        if not valid:
            raise ValueError(f"corrida sem vazão positiva aproveitável: {path.name}")
        rates[path.name] = median(valid)
    if not rates:
        raise ValueError(f"nenhum CSV bench_features encontrado em {directory}")
    return rates


def load_bench_calibration(path: Path) -> dict[str, object]:
    calibration = json.loads(path.read_text(encoding="utf-8"))
    rates = calibration.get("median_active_flow_liters_minute", {})
    if not rates or any(not math.isfinite(rate) or rate <= 0 for rate in rates.values()):
        raise ValueError("calibração sem vazões positivas e finitas")
    return calibration


def simulate_household(
    rows: list[dict[str, str]],
    rates: list[float],
    *,
    seed: int,
    interval_minutes: int,
    timezone: str,
    profile: str,
) -> list[dict[str, str]]:
    """Simulate intermittent use and retain the mock's labelled scenarios."""
    rng = random.Random(seed)
    local_zone = ZoneInfo(timezone)
    cumulative = BASE_VOLUME_LITERS
    increment = mock.ANOMALY_INCREMENT[profile]
    for row in rows:
        local = datetime.fromisoformat(row["recorded_at"]).astimezone(local_zone)
        present = row["reading_present"] == "1"
        anomalous = row["scenario_label"] in {"continuous_flow", "night_consumption"}
        background = (
            max(0.0, float(row["flow_rate_liters_minute"]) - (increment if anomalous else 0))
            if present else mock._flow(local.hour, rng, profile)
        )
        if local.weekday() >= 5 and 8 <= local.hour < 18:
            background *= 1.2
        rate = rng.choice(rates)
        # Average one synthetic use event over the entire reporting interval.
        active_fraction = rng.uniform(0.1, 1)
        probability = min(1.0, background / (rate * 0.55))
        flow = rate * active_fraction if rng.random() < probability else 0.0
        if anomalous:
            flow += increment
        flow = round(flow, 3)
        cumulative = round(cumulative + flow * interval_minutes, 3)
        if present:
            row["flow_rate_liters_minute"] = f"{flow:.3f}"
            row["cumulative_volume_liters"] = f"{cumulative:.3f}"
            row["firmware_version"] = "bench-sim-1"
    return rows


def load_real_pools(real_csv: Path) -> dict[str, list[float]]:
    """Agrupa as vazões reais válidas por cenário (saída do exportador)."""
    pools: dict[str, list[float]] = defaultdict(list)
    with Path(real_csv).open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {"scenario_label", "flow_rate_liters_minute"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV real sem colunas obrigatórias: {sorted(missing)}")
        for row in reader:
            quality = (row.get("quality") or "valid").strip()
            if quality not in VALID_QUALITY:
                continue
            flow_text = (row.get("flow_rate_liters_minute") or "").strip()
            if not flow_text:
                continue
            scenario = (row.get("scenario_label") or "").strip()
            pools[scenario].append(float(flow_text))
    return dict(pools)


def _sample(rng: random.Random, pools: dict[str, list[float]], scenario: str) -> float:
    values = pools.get(scenario)
    if not values:
        raise ValueError(
            f"sem vazão real para o cenário {scenario!r}; colete leituras desse cenário"
        )
    return rng.choice(values)


def inject(
    skeleton_rows: list[dict[str, str]],
    pools: dict[str, list[float]],
    *,
    seed: int,
    interval_minutes: int,
) -> list[dict[str, str]]:
    """Substitui a vazão sintética pela real e recomputa o volume acumulado."""
    rng = random.Random(seed)
    cumulative = BASE_VOLUME_LITERS
    result: list[dict[str, str]] = []
    for row in skeleton_rows:
        new_row = dict(row)
        scenario = row["scenario_label"]
        if int(row["reading_present"]):
            flow = _sample(rng, pools, scenario)
            cumulative += flow * interval_minutes
            new_row["flow_rate_liters_minute"] = f"{flow:.3f}"
            new_row["cumulative_volume_liters"] = f"{cumulative:.3f}"
        else:
            # O dispositivo não transmitiu (lacuna). Mantém a linha vazia, mas
            # avança o contador com uma vazão normal plausível para que o volume
            # após a lacuna permaneça coerente.
            cumulative += _sample(rng, pools, "normal") * interval_minutes
        result.append(new_row)
    return result


def build(
    real_csv: Path | None,
    output: Path,
    *,
    seed: int,
    start,
    days: int,
    interval_minutes: int,
    timezone: str,
    profile: str = "standard",
    bench_dir: Path | None = None,
    exclude_flows: list[float] | None = None,
    calibration: Path | None = None,
    bench_calibration: Path | None = None,
) -> dict[str, object]:
    """Gera o esqueleto do mock e injeta a vazão real; grava o CSV e o manifesto."""
    if sum(source is not None for source in (real_csv, bench_dir, calibration)) != 1:
        raise ValueError("informe exatamente uma fonte de vazão")
    exclusions = exclude_flows or []
    pools = load_real_pools(real_csv) if real_csv is not None else {}
    calibration_data: dict[str, object] = {}
    active_calibration = calibration or bench_calibration
    if calibration is not None:
        calibration_data = load_bench_calibration(calibration)
        bench_rates = calibration_data["median_active_flow_liters_minute"]
    elif bench_dir is not None:
        calibration_data = load_bench_calibration(bench_calibration or DEFAULT_CALIBRATION)
        excluded = calibration_data.get("excluded_measurements", {})
        bench_rates = load_bench_rates(
            bench_dir,
            exclusions,
            excluded if isinstance(excluded, dict) else {},
        )
        expected_rates = calibration_data["median_active_flow_liters_minute"]
        if set(bench_rates) != set(expected_rates) or any(
            not math.isclose(bench_rates[name], expected_rates[name], abs_tol=0.005)
            for name in bench_rates
        ):
            raise ValueError("CSV de bancada não corresponde às medianas da calibração versionada")
    else:
        bench_rates = {}
    with tempfile.TemporaryDirectory() as tmp:
        skeleton_path = Path(tmp) / "skeleton.csv"
        mock.generate(
            skeleton_path,
            seed=seed,
            start=start,
            days=days,
            interval_minutes=interval_minutes,
            timezone=timezone,
            profile=profile,
        )
        with skeleton_path.open(newline="", encoding="utf-8") as source:
            skeleton_rows = list(csv.DictReader(source))

    rows = (
        simulate_household(
            skeleton_rows, list(bench_rates.values()), seed=seed,
            interval_minutes=interval_minutes, timezone=timezone, profile=profile,
        )
        if bench_rates
        else inject(skeleton_rows, pools, seed=seed, interval_minutes=interval_minutes)
    )

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=mock.FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "source_real_csv": str(real_csv),
        "output_file": output.name,
        "generated_rows": len(rows),
        "base_volume_liters": BASE_VOLUME_LITERS,
        "pool_sizes": {scenario: len(values) for scenario, values in sorted(pools.items())},
        "skeleton": {
            "seed": seed,
            "start": start.isoformat(),
            "days": days,
            "interval_minutes": interval_minutes,
            "timezone": timezone,
            "profile": profile,
        },
        "policy": (
            "Somente flow_rate_liters_minute e cumulative_volume_liters derivam da coleta "
            "real; recorded_at, cenário, event_id e metadados de dispositivo vêm do "
            "esqueleto sintético do mock. Vazão amostrada de forma independente por "
            "intervalo (sem preservar autocorrelação). Bateria e sinal são sintéticos e "
            "não são features. Não comprova detecção de vazamento real."
        ),
    }
    if bench_rates:
        manifest.update(
            source_real_csv=None,
            source_bench_dir=str(bench_dir) if bench_dir is not None else None,
            median_active_flow_liters_minute=bench_rates,
            excluded_flow_values=exclusions,
            weekend_daytime_background_multiplier=1.2,
            policy=(
                "Série híbrida: medianas de vazão positiva por corrida calibram os eventos "
                "de uso. Duração, frequência, calendário, rótulos e fluxo anômalo adicional "
                "são simulados. A condição da bancada não define o rótulo. A exclusão por "
                "valor não identifica todos os sopros. Não valida detecção em campo."
            ),
        )
    if active_calibration is not None:
        manifest["source_calibration"] = active_calibration.name
        manifest["excluded_measurements"] = calibration_data["excluded_measurements"]
    (output.parent / "build_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--real", type=Path)
    source.add_argument("--bench-dir", type=Path)
    source.add_argument("--calibration", type=Path, nargs="?", const=DEFAULT_CALIBRATION)
    parser.add_argument("--bench-calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--exclude-flow", type=float, action="append", default=[])
    parser.add_argument("--output", type=Path, default=Path("data/ml/real/readings.csv"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", type=mock._start, default=mock._start("2026-09-01T00:00:00-03:00"))
    parser.add_argument("--timezone", default="America/Sao_Paulo")
    parser.add_argument("--days", type=int, default=16)
    parser.add_argument("--interval-minutes", type=int, default=5)
    parser.add_argument("--profile", choices=("standard", "shifted", "stress"), default="standard")
    args = parser.parse_args()
    manifest = build(
        None if args.bench_dir or args.calibration
        else args.real or Path("data/ml/real/readings_rotulados.csv"),
        args.output,
        seed=args.seed,
        start=args.start,
        days=args.days,
        interval_minutes=args.interval_minutes,
        timezone=args.timezone,
        profile=args.profile,
        bench_dir=args.bench_dir,
        exclude_flows=args.exclude_flow,
        calibration=args.calibration,
        bench_calibration=args.bench_calibration,
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
