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
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models import Device, TelemetryLabel, TelemetryReading
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


async def _readings_in_window(session: AsyncSession, window: LabelWindow) -> list[TelemetryReading]:
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


def _write_csv(
    rows: list[dict[str, Any]], output_path: Path, fields: tuple[str, ...] = OUTPUT_FIELDS
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
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


def _parse_instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.utcoffset() is None:
        raise ValueError("informe data e hora com fuso explícito")
    return instant.astimezone(UTC)


async def export_reviewed(
    factory: async_sessionmaker[AsyncSession],
    device_id: UUID,
    start: datetime,
    end: datetime,
    origin: str,
    output: Path,
) -> int:
    """Exporta as revisões vigentes em um intervalo semiaberto, sem alterar as leituras."""
    if start.utcoffset() is None or end.utcoffset() is None or start >= end:
        raise ValueError("intervalo inválido: use início e fim com fuso, em ordem crescente")
    if origin not in {"physical", "simulated"}:
        raise ValueError("declare a origem da coleta: physical ou simulated")
    latest = (
        select(TelemetryLabel.id)
        .where(TelemetryLabel.reading_id == TelemetryReading.id)
        .order_by(TelemetryLabel.reviewed_at.desc(), TelemetryLabel.id.desc())
        .limit(1)
        .correlate(TelemetryReading)
        .scalar_subquery()
    )
    rows = []
    excluded: dict[str, int] = {}
    async with factory() as session:
        device = await session.get(Device, device_id)
        if device is None:
            raise ValueError("medidor não encontrado")
        records = await session.execute(
            select(TelemetryReading, TelemetryLabel)
            .outerjoin(TelemetryLabel, TelemetryLabel.id == latest)
            .where(
                TelemetryReading.device_id == device_id,
                TelemetryReading.recorded_at >= start,
                TelemetryReading.recorded_at < end,
            )
            .order_by(TelemetryReading.recorded_at, TelemetryReading.id)
        )
        for reading, review in records:
            if review is None or review.label not in {"normal", "anomaly"}:
                reason = review.label if review is not None else "unlabeled"
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            rows.append(
                {
                    "reading_id": str(reading.id),
                    "event_id": reading.event_id,
                    "recorded_at": _as_utc(reading.recorded_at).isoformat(),
                    "cumulative_volume_liters": _decimal_field(reading.cumulative_volume_liters),
                    "flow_rate_liters_minute": _decimal_field(reading.flow_rate_liters_minute),
                    "quality": reading.quality,
                    "review_id": str(review.id),
                    "anomaly_label": int(review.label == "anomaly"),
                }
            )
        interval = device.expected_interval_seconds

    _write_csv(
        rows,
        output,
        (
            "reading_id",
            "event_id",
            "recorded_at",
            "cumulative_volume_liters",
            "flow_rate_liters_minute",
            "quality",
            "review_id",
            "anomaly_label",
        ),
    )
    manifest = {
        "schema_version": 1,
        "stage": "reviewed_telemetry_export",
        "declared_origin": origin,
        "label_source": "administrator_review",
        "device_id": str(device_id),
        "expected_interval_seconds": interval,
        "start": start.astimezone(UTC).isoformat(),
        "end_exclusive": end.astimezone(UTC).isoformat(),
        "exported": len(rows),
        "excluded_by_review_status": excluded,
        "sha256": sha256(await asyncio.to_thread(output.read_bytes)).hexdigest(),
    }
    await asyncio.to_thread(
        output.with_suffix(output.suffix + ".json").write_text,
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(rows)


async def _amain(args: argparse.Namespace) -> None:
    factory = create_session_factory(settings)
    try:
        if args.device_id is None:
            count = len(await export(factory, args.sheet, args.output, args.timezone))
        else:
            count = await export_reviewed(
                factory, args.device_id, args.start, args.end, args.origin, args.output
            )
        print(f"{count} leituras rotuladas exportadas para {args.output}")
    finally:
        bind = factory.kw.get("bind")
        if bind is not None:
            await bind.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, default=Path("ml/collection/rotulos-template.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml/real/readings_rotulados.csv"))
    parser.add_argument("--timezone", default="America/Sao_Paulo")
    parser.add_argument("--device-id", type=UUID, help="Exporta rótulos revisados no banco")
    parser.add_argument("--start", type=_parse_instant)
    parser.add_argument("--end", type=_parse_instant)
    parser.add_argument("--origin", choices=("physical", "simulated"))
    args = parser.parse_args()
    if args.device_id is not None and not all((args.start, args.end, args.origin)):
        parser.error("--device-id exige --start, --end e --origin")
    if args.device_id is None and any((args.start, args.end, args.origin)):
        parser.error("--start, --end e --origin exigem --device-id")
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
