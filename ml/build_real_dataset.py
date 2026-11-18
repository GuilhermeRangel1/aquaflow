"""Monta o CSV de treino injetando vazão real no esqueleto temporal do mock.

Reusa ``generate_mock_data`` para o esqueleto (dias, cadência e agenda de
cenários) e substitui a vazão sintética pela vazão real medida — a saída do
exportador do backend (``backend/app/export_training_data.py``). Apenas a vazão
e o volume acumulado derivado são reais; horário, cenário, ``event_id`` e os
metadados de dispositivo vêm do esqueleto. Isto não decide vazamento: só monta
o dataset preservando a origem real das medições de vazão.

Limitações registradas: a vazão é amostrada de forma independente por intervalo
a partir do pool real de cada cenário, então a autocorrelação temporal das
corridas reais não é preservada; bateria e sinal continuam sintéticos e não são
features. As métricas resultantes não comprovam detecção de vazamento real.
"""

import argparse
import csv
import json
import random
import tempfile
from collections import defaultdict
from pathlib import Path

import generate_mock_data as mock

VALID_QUALITY = {"valid"}
BASE_VOLUME_LITERS = 1000.0


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
    real_csv: Path,
    output: Path,
    *,
    seed: int,
    start,
    days: int,
    interval_minutes: int,
    timezone: str,
    profile: str = "standard",
) -> dict[str, object]:
    """Gera o esqueleto do mock e injeta a vazão real; grava o CSV e o manifesto."""
    pools = load_real_pools(real_csv)
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

    rows = inject(skeleton_rows, pools, seed=seed, interval_minutes=interval_minutes)

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
    (output.parent / "build_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real", type=Path, default=Path("data/ml/real/readings_rotulados.csv")
    )
    parser.add_argument("--output", type=Path, default=Path("data/ml/real/readings.csv"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start", type=mock._start, default=mock._start("2026-09-01T00:00:00-03:00"))
    parser.add_argument("--timezone", default="America/Sao_Paulo")
    parser.add_argument("--days", type=int, default=16)
    parser.add_argument("--interval-minutes", type=int, default=5)
    parser.add_argument("--profile", choices=("standard", "shifted", "stress"), default="standard")
    args = parser.parse_args()
    manifest = build(
        args.real,
        args.output,
        seed=args.seed,
        start=args.start,
        days=args.days,
        interval_minutes=args.interval_minutes,
        timezone=args.timezone,
        profile=args.profile,
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
