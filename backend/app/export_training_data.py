"""Export labeled real telemetry to a CSV for the real-data ML pipeline.

Lê leituras brutas da persistência (``telemetry_readings``) e as cruza com uma
planilha de rótulos preenchida à mão (ver ``ml/collection/protocolo-coleta.md``).
Cada corrida da planilha descreve uma janela de tempo local e o cenário; este
script aplica o rótulo às leituras daquele dispositivo dentro da janela.

A saída alimenta o *builder* do ``ml/`` que injeta a vazão real no esqueleto
temporal do mock. Aqui não se decide vazamento: só se rotula e se preserva a
leitura bruta. O script é somente leitura no banco.
"""

import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models import Device, TelemetryReading
from app.db.session import create_session_factory

SCENARIOS = ("normal", "continuous_flow", "night_consumption", "missing_reading")
REQUIRED_COLUMNS = {"corrida", "device_serial", "inicio_local", "fim_local", "cenario"}
TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
OUTPUT_FIELDS = (
    "corrida",
    "device_serial",
    "event_id",
    "recorded_at",
    "cumulative_volume_liters",
    "flow_rate_liters_minute",
    "quality",
    "scenario_label",
    "anomaly_label",
)


@dataclass(frozen=True)
class LabelWindow:
    """Uma corrida da planilha, com a janela já normalizada para UTC."""

    corrida: str
    device_serial: str
    start_utc: datetime
    end_utc: datetime
    scenario_label: str
    anomaly_label: int


def _parse_local(value: str, timezone: str) -> datetime:
    text = value.strip()
    for fmt in TIME_FORMATS:
        try:
            naive = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=ZoneInfo(timezone)).astimezone(UTC)
    raise ValueError(f"horário inválido: {value!r} (use AAAA-MM-DD HH:MM)")


def _as_utc(value: datetime) -> datetime:
    """Trata leituras sem fuso (ex.: SQLite) como UTC, converte as demais."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _check_no_overlap(windows: list[LabelWindow]) -> None:
    by_device: dict[str, list[LabelWindow]] = {}
    for window in windows:
        by_device.setdefault(window.device_serial, []).append(window)
    for device_windows in by_device.values():
        ordered = sorted(device_windows, key=lambda w: w.start_utc)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start_utc < previous.end_utc:
                raise ValueError(
                    "janelas sobrepostas no mesmo dispositivo: "
                    f"corridas {previous.corrida} e {current.corrida} "
                    f"({previous.device_serial})"
                )


def load_label_sheet(path: Path, timezone: str) -> list[LabelWindow]:
    """Lê e valida a planilha de rótulos; devolve janelas normalizadas em UTC."""
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"timezone IANA desconhecido: {timezone}") from error

    windows: list[LabelWindow] = []
    with Path(path).open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"colunas obrigatórias ausentes: {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            corrida = (row.get("corrida") or "").strip()
            serial = (row.get("device_serial") or "").strip()
            scenario = (row.get("cenario") or "").strip()
            if not corrida or not serial:
                raise ValueError(f"linha {line}: corrida e device_serial são obrigatórios")
            if scenario not in SCENARIOS:
                raise ValueError(f"linha {line}: cenário desconhecido: {scenario!r}")
            try:
                start = _parse_local(row["inicio_local"], timezone)
                end = _parse_local(row["fim_local"], timezone)
            except ValueError as error:
                raise ValueError(f"linha {line}: {error}") from error
            if end <= start:
                raise ValueError(f"linha {line}: fim deve ser depois do início")
            windows.append(
                LabelWindow(
                    corrida=corrida,
                    device_serial=serial,
                    start_utc=start,
                    end_utc=end,
                    scenario_label=scenario,
                    anomaly_label=int(scenario != "normal"),
                )
            )
    _check_no_overlap(windows)
    return windows


def _decimal_field(value: Any) -> str:
    return "" if value is None else str(value)


def _row(window: LabelWindow, reading: TelemetryReading) -> dict[str, Any]:
    recorded = _as_utc(reading.recorded_at).isoformat().replace("+00:00", "Z")
    return {
        "corrida": window.corrida,
        "device_serial": window.device_serial,
        "event_id": reading.event_id,
        "recorded_at": recorded,
        "cumulative_volume_liters": _decimal_field(reading.cumulative_volume_liters),
        "flow_rate_liters_minute": _decimal_field(reading.flow_rate_liters_minute),
        "quality": reading.quality,
        "scenario_label": window.scenario_label,
        "anomaly_label": window.anomaly_label,
    }


async def _readings_in_window(
    session: AsyncSession, window: LabelWindow
) -> list[TelemetryReading]:
    statement = (
        select(TelemetryReading)
        .join(Device, TelemetryReading.device_id == Device.id)
        .where(
            Device.serial_number == window.device_serial,
            TelemetryReading.recorded_at >= window.start_utc,
            TelemetryReading.recorded_at <= window.end_utc,
        )
        .order_by(TelemetryReading.recorded_at)
    )
    return list((await session.scalars(statement)).all())


def _write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


async def export(
    session_factory: async_sessionmaker[AsyncSession],
    sheet_path: Path,
    output_path: Path,
    timezone: str,
) -> list[dict[str, Any]]:
    """Rotula as leituras reais de cada janela e grava o CSV. Retorna as linhas."""
    windows = load_label_sheet(sheet_path, timezone)
    rows: list[dict[str, Any]] = []
    async with session_factory() as session:
        for window in windows:
            for reading in await _readings_in_window(session, window):
                rows.append(_row(window, reading))
    _write_csv(rows, output_path)
    return rows


async def _amain(sheet_path: Path, output_path: Path, timezone: str) -> None:
    factory = create_session_factory(settings)
    try:
        rows = await export(factory, sheet_path, output_path, timezone)
        print(f"{len(rows)} leituras rotuladas exportadas para {output_path}")
    finally:
        bind = factory.kw.get("bind")
        if bind is not None:
            await bind.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sheet", type=Path, default=Path("ml/collection/rotulos-template.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/ml/real/readings_rotulados.csv")
    )
    parser.add_argument("--timezone", default="America/Sao_Paulo")
    args = parser.parse_args()
    asyncio.run(_amain(args.sheet, args.output, args.timezone))


if __name__ == "__main__":
    main()
