from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_device_key
from app.db.models import Device, Property, TelemetryReading
from app.db.session import get_session
from app.schemas.telemetry import (
    BatchTelemetryInput,
    BatchTelemetryOutput,
    TelemetryAccepted,
    TelemetryInput,
)
from app.services.anomaly_detection import evaluate_continuous_flow, evaluate_night_consumption
from app.services.device_monitor import resolve_offline_alerts

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


class IngestionFailure(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


@router.post("/telemetry", status_code=202, response_model=TelemetryAccepted)
async def ingest_telemetry(
    payload: TelemetryInput,
    request: Request,
    device_key: str | None = Header(default=None, alias="X-Device-Key"),
    session: AsyncSession = Depends(get_session),
) -> TelemetryAccepted:
    if not device_key:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_device_key", "message": "Device credentials are required"},
        )
    try:
        return await save_reading(session, payload, device_key, request.app.state.settings)
    except IngestionFailure as failure:
        raise HTTPException(
            status_code=failure.status_code,
            detail={"code": failure.code, "message": failure.message},
        ) from None


@router.post("/telemetry/batch", response_model=BatchTelemetryOutput)
async def ingest_batch(
    payload: BatchTelemetryInput,
    request: Request,
    device_key: str | None = Header(default=None, alias="X-Device-Key"),
    session: AsyncSession = Depends(get_session),
) -> BatchTelemetryOutput:
    if not device_key:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_device_key", "message": "Device credentials are required"},
        )

    results: list[TelemetryAccepted] = []
    for item in payload.items:
        event_id = str(item.get("event_id", ""))[:80]
        try:
            reading = TelemetryInput.model_validate(item)
            results.append(
                await save_reading(session, reading, device_key, request.app.state.settings)
            )
        except ValidationError:
            results.append(
                TelemetryAccepted(
                    reading_id=None,
                    event_id=event_id,
                    status="rejected",
                    code="invalid_payload",
                    message="Telemetry item does not match the expected schema",
                )
            )
        except IngestionFailure as failure:
            if failure.status_code == 401:
                raise HTTPException(
                    status_code=failure.status_code,
                    detail={"code": failure.code, "message": failure.message},
                ) from None
            results.append(
                TelemetryAccepted(
                    reading_id=None,
                    event_id=event_id,
                    status="rejected",
                    code=failure.code,
                    message=failure.message,
                )
            )
    return BatchTelemetryOutput(items=results)


async def save_reading(
    session: AsyncSession,
    payload: TelemetryInput,
    device_key: str,
    config: Any,
) -> TelemetryAccepted:
    now = datetime.now(UTC)
    recorded_at = payload.recorded_at.astimezone(UTC)
    key_hash = hash_device_key(device_key)
    async with session.begin():
        device = await session.scalar(
            select(Device)
            .join(Property, Property.id == Device.property_id)
            .where(
                Device.serial_number == payload.device_serial,
                Device.device_key_hash == key_hash,
                Device.is_active.is_(True),
            )
        )
        if device is None:
            raise IngestionFailure(401, "invalid_device_key", "Device credentials are invalid")

        existing = await session.scalar(
            select(TelemetryReading).where(
                TelemetryReading.device_id == device.id,
                TelemetryReading.event_id == payload.event_id,
            )
        )
        if existing is not None:
            return TelemetryAccepted(
                reading_id=existing.id,
                event_id=existing.event_id,
                status="duplicate",
                duplicate=True,
                normalized_at=existing.recorded_at,
            )

        if recorded_at > now + timedelta(seconds=config.future_clock_skew_seconds):
            raise IngestionFailure(
                422, "timestamp_too_far_in_future", "Reading timestamp is too far in the future"
            )

        property_row = await session.get(Property, device.property_id)
        if property_row is None:
            raise IngestionFailure(401, "invalid_device_key", "Device credentials are invalid")
        late_days = device.late_reading_window_days or property_row.late_reading_window_days
        if recorded_at < now - timedelta(days=late_days):
            raise IngestionFailure(
                422,
                "reading_outside_accepted_window",
                "Reading is older than the configured acceptance window",
            )

        latest = await session.scalar(
            select(TelemetryReading)
            .where(TelemetryReading.device_id == device.id)
            .order_by(TelemetryReading.recorded_at.desc())
            .limit(1)
        )
        quality = "valid"
        if latest is not None and recorded_at < _as_utc(latest.recorded_at):
            quality = "out_of_order"
        elif (
            latest is not None
            and payload.cumulative_volume_liters is not None
            and latest.cumulative_volume_liters is not None
            and payload.cumulative_volume_liters < latest.cumulative_volume_liters
        ):
            quality = "counter_reset"

        reading = TelemetryReading(
            device_id=device.id,
            event_id=payload.event_id,
            recorded_at=recorded_at,
            received_at=now,
            cumulative_volume_liters=(
                Decimal(str(payload.cumulative_volume_liters))
                if payload.cumulative_volume_liters is not None
                else None
            ),
            flow_rate_liters_minute=(
                Decimal(str(payload.flow_rate_liters_minute))
                if payload.flow_rate_liters_minute is not None
                else None
            ),
            quality=quality,
            battery_percent=payload.battery_percent,
            signal_dbm=payload.signal_dbm,
            firmware_version=payload.firmware_version,
        )
        session.add(reading)
        if device.last_seen_at is None or _as_utc(device.last_seen_at) < now:
            device.last_seen_at = now
        await session.flush()
        await resolve_offline_alerts(session, device, now=now)
        if quality == "valid":
            await evaluate_continuous_flow(
                session,
                device=device,
                property_row=property_row,
                through=recorded_at,
            )
            await evaluate_night_consumption(
                session,
                device=device,
                property_row=property_row,
                through=recorded_at,
            )
        return TelemetryAccepted(
            reading_id=reading.id,
            event_id=reading.event_id,
            status="accepted",
            duplicate=False,
            normalized_at=recorded_at,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
