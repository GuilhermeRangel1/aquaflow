from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from math import ceil
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cursors import decode_timestamp, encode_timestamp
from app.api.deps import current_user
from app.db.models import Alert, AnomalyEvent, Device, Property, TelemetryReading, User
from app.db.session import get_session
from app.domain.consumption import Sample, aggregate_samples, interval_volume

router = APIRouter(prefix="/api/v1/properties", tags=["consumption"])


class ConsumptionItem(BaseModel):
    bucket_start: datetime
    volume_liters: float
    sample_count: int = Field(ge=1)


class ConsumptionSummary(BaseModel):
    total_volume_liters: float
    valid_interval_count: int
    previous_period_total_volume_liters: float | None = None
    change_volume_liters: float | None = None
    change_percent: float | None = None
    average_daily_volume_liters: float | None = Field(
        default=None, description="Mean over local days containing at least one valid interval."
    )
    average_hourly_volume_liters: float | None = Field(
        default=None, description="Mean over local hours containing at least one valid interval."
    )
    maximum_interval_volume_liters: float | None = Field(
        default=None, description="Largest valid interval volume clipped to the requested range."
    )
    valid_data_percentage: float | None = Field(
        default=None,
        description=(
            "Valid intervals divided by expected intervals for active devices, capped at 100."
        ),
    )
    expected_interval_count: int = Field(
        description="Expected sampling intervals for active devices in the requested range."
    )
    days_with_valid_data: int = Field(description="Local calendar days with a valid interval.")
    hours_with_valid_data: int = Field(description="Local calendar hours with a valid interval.")
    last_reading_at: datetime | None = Field(
        default=None, description="Latest raw reading timestamp inside the requested range."
    )
    open_alert_count: int = Field(description="Alerts in open or acknowledged state.")


class ConsumptionResponse(BaseModel):
    items: list[ConsumptionItem]
    limit: int
    cursor: str | None = None
    has_more: bool = False
    summary: ConsumptionSummary


@router.get("/{property_id}/consumption", response_model=ConsumptionResponse)
async def get_consumption(
    property_id: UUID,
    start: datetime,
    end: datetime,
    granularity: Literal["hour", "day", "month"] = "hour",
    limit: int = Query(default=1000, ge=1, le=2000),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ConsumptionResponse:
    if (
        start.tzinfo is None
        or start.utcoffset() is None
        or end.tzinfo is None
        or end.utcoffset() is None
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "timezone_required",
                "message": "start and end must include a timezone",
            },
        )
    start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
    if start_utc >= end_utc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_range", "message": "start must be before end"}
        )

    property_row = await session.scalar(
        select(Property).where(Property.id == property_id, Property.owner_id == user.id)
    )
    if property_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "property_not_found", "message": "Property was not found"},
        )
    devices = list(
        (await session.scalars(select(Device).where(Device.property_id == property_row.id))).all()
    )
    if not devices:
        return empty_response(limit)

    device_ids = [device.id for device in devices]
    max_lookback = max(device.expected_interval_seconds * 2 for device in devices)
    previous_start = start_utc - (end_utc - start_utc)
    readings = list(
        (
            await session.scalars(
                select(TelemetryReading)
                .where(
                    TelemetryReading.device_id.in_(device_ids),
                    TelemetryReading.recorded_at
                    >= previous_start - timedelta(seconds=max_lookback),
                    TelemetryReading.recorded_at <= end_utc,
                )
                .order_by(TelemetryReading.device_id, TelemetryReading.recorded_at)
            )
        ).all()
    )
    device_by_id = {device.id: device for device in devices}
    samples_by_device: dict[UUID, list[Sample]] = {device.id: [] for device in devices}
    for reading in readings:
        # Invalid/reset/out-of-order observations remain available in the raw
        # history, but must not contribute to derived consumption.
        if reading.quality != "valid":
            continue
        samples_by_device[reading.device_id].append(
            Sample(
                recorded_at=reading.recorded_at.replace(tzinfo=UTC)
                if reading.recorded_at.tzinfo is None
                else reading.recorded_at,
                cumulative_volume_liters=reading.cumulative_volume_liters,
                flow_rate_liters_minute=reading.flow_rate_liters_minute,
            )
        )

    current_totals = _aggregate_period(
        samples_by_device,
        device_by_id,
        property_row.timezone,
        granularity,
        start=start_utc,
        end=end_utc,
    )
    previous_totals = _aggregate_period(
        samples_by_device,
        device_by_id,
        property_row.timezone,
        granularity,
        start=previous_start,
        end=start_utc,
    )
    ordered = sorted(current_totals.items())
    total = sum((value[0] for _, value in ordered), Decimal(0))
    previous_total = sum((value[0] for value in previous_totals.values()), Decimal(0))
    change = total - previous_total
    if cursor is not None:
        try:
            cursor_at = decode_timestamp(cursor).astimezone(UTC)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_cursor", "message": "Cursor is invalid"},
            ) from None
        ordered = [(bucket, value) for bucket, value in ordered if bucket > cursor_at]
    page = ordered[:limit]
    has_more = len(ordered) > limit

    daily_totals = _aggregate_period(
        samples_by_device,
        device_by_id,
        property_row.timezone,
        "day",
        start=start_utc,
        end=end_utc,
    )
    hourly_totals = _aggregate_period(
        samples_by_device,
        device_by_id,
        property_row.timezone,
        "hour",
        start=start_utc,
        end=end_utc,
    )
    interval_count, maximum_interval, expected_interval_count = _interval_metrics(
        samples_by_device,
        devices,
        start=start_utc,
        end=end_utc,
    )
    open_alert_count = await session.scalar(
        select(func.count(Alert.id))
        .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
        .where(
            AnomalyEvent.property_id == property_row.id,
            Alert.status.in_(["open", "acknowledged"]),
        )
    )
    last_reading_at = max(
        (
            reading.recorded_at.replace(tzinfo=UTC)
            if reading.recorded_at.tzinfo is None
            else reading.recorded_at.astimezone(UTC)
            for reading in readings
            if start_utc <= _as_utc(reading.recorded_at) < end_utc
        ),
        default=None,
    )
    days_with_data = len(daily_totals)
    hours_with_data = len(hourly_totals)
    return ConsumptionResponse(
        items=[
            ConsumptionItem(
                bucket_start=bucket_start,
                volume_liters=float(value[0].quantize(Decimal("0.001"))),
                sample_count=value[1],
            )
            for bucket_start, value in page
        ],
        limit=limit,
        cursor=encode_timestamp(page[-1][0]) if has_more and page else None,
        has_more=has_more,
        summary=ConsumptionSummary(
            total_volume_liters=float(total.quantize(Decimal("0.001"))),
            valid_interval_count=interval_count,
            previous_period_total_volume_liters=float(previous_total.quantize(Decimal("0.001"))),
            change_volume_liters=float(change.quantize(Decimal("0.001"))),
            change_percent=(
                float((change / previous_total * Decimal(100)).quantize(Decimal("0.1")))
                if previous_total > 0
                else None
            ),
            average_daily_volume_liters=(
                float((total / days_with_data).quantize(Decimal("0.001")))
                if days_with_data
                else None
            ),
            average_hourly_volume_liters=(
                float((total / hours_with_data).quantize(Decimal("0.001")))
                if hours_with_data
                else None
            ),
            maximum_interval_volume_liters=(
                float(maximum_interval.quantize(Decimal("0.001")))
                if maximum_interval is not None
                else None
            ),
            valid_data_percentage=(
                round(min(100.0, interval_count / expected_interval_count * 100), 1)
                if expected_interval_count
                else None
            ),
            expected_interval_count=expected_interval_count,
            days_with_valid_data=days_with_data,
            hours_with_valid_data=hours_with_data,
            last_reading_at=last_reading_at,
            open_alert_count=int(open_alert_count or 0),
        ),
    )


def _aggregate_period(
    samples_by_device: dict[UUID, list[Sample]],
    device_by_id: dict[UUID, Device],
    timezone_name: str,
    granularity: Literal["hour", "day", "month"],
    *,
    start: datetime,
    end: datetime,
) -> dict[datetime, tuple[Decimal, int]]:
    totals: dict[datetime, tuple[Decimal, int]] = {}
    for device_id, samples in samples_by_device.items():
        buckets = aggregate_samples(
            samples,
            device_by_id[device_id].expected_interval_seconds,
            timezone_name,
            granularity,
            start=start,
            end=end,
        )
        for bucket in buckets:
            volume, count = totals.get(bucket.bucket_start, (Decimal(0), 0))
            totals[bucket.bucket_start] = (
                volume + bucket.volume_liters,
                count + bucket.sample_count,
            )
    return totals


def empty_response(limit: int) -> ConsumptionResponse:
    return ConsumptionResponse(
        items=[],
        limit=limit,
        summary=ConsumptionSummary(
            total_volume_liters=0,
            valid_interval_count=0,
            previous_period_total_volume_liters=0,
            change_volume_liters=0,
            change_percent=None,
            average_daily_volume_liters=None,
            average_hourly_volume_liters=None,
            maximum_interval_volume_liters=None,
            valid_data_percentage=None,
            expected_interval_count=0,
            days_with_valid_data=0,
            hours_with_valid_data=0,
            last_reading_at=None,
            open_alert_count=0,
        ),
    )


def _interval_metrics(
    samples_by_device: dict[UUID, list[Sample]],
    devices: list[Device],
    *,
    start: datetime,
    end: datetime,
) -> tuple[int, Decimal | None, int]:
    count = 0
    maximum: Decimal | None = None
    expected_count = sum(
        ceil((end - start).total_seconds() / device.expected_interval_seconds)
        for device in devices
        if device.is_active
    )
    for device in devices:
        samples = samples_by_device[device.id]
        for previous, current in pairwise(samples):
            volume = interval_volume(previous, current, device.expected_interval_seconds)
            if volume is None:
                continue
            previous_at, current_at = _as_utc(previous.recorded_at), _as_utc(current.recorded_at)
            overlap_start, overlap_end = max(start, previous_at), min(end, current_at)
            if overlap_end <= overlap_start:
                continue
            duration = Decimal(str((current_at - previous_at).total_seconds()))
            overlap = Decimal(str((overlap_end - overlap_start).total_seconds()))
            clipped_volume = volume * overlap / duration
            count += 1
            maximum = clipped_volume if maximum is None else max(maximum, clipped_volume)
    return count, maximum, expected_count


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
