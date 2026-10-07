from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.models import Device, Property, TelemetryReading, User
from app.db.session import get_session
from app.domain.consumption import Sample, aggregate_samples

router = APIRouter(prefix="/api/v1/properties", tags=["consumption"])


class ConsumptionItem(BaseModel):
    bucket_start: datetime
    volume_liters: float
    sample_count: int = Field(ge=1)


class ConsumptionSummary(BaseModel):
    total_volume_liters: float
    valid_interval_count: int


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
    readings = list(
        (
            await session.scalars(
                select(TelemetryReading)
                .where(
                    TelemetryReading.device_id.in_(device_ids),
                    TelemetryReading.recorded_at >= start_utc - timedelta(seconds=max_lookback),
                    TelemetryReading.recorded_at <= end_utc,
                )
                .order_by(TelemetryReading.device_id, TelemetryReading.recorded_at)
            )
        ).all()
    )
    device_by_id = {device.id: device for device in devices}
    samples_by_device: dict[UUID, list[Sample]] = {device.id: [] for device in devices}
    for reading in readings:
        if reading.quality == "counter_reset":
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

    totals: dict[datetime, tuple[Decimal, int]] = {}
    for device_id, samples in samples_by_device.items():
        buckets = aggregate_samples(
            samples,
            device_by_id[device_id].expected_interval_seconds,
            property_row.timezone,
            granularity,
            start=start_utc,
            end=end_utc,
        )
        for bucket in buckets:
            volume, count = totals.get(bucket.bucket_start, (Decimal(0), 0))
            totals[bucket.bucket_start] = (
                volume + bucket.volume_liters,
                count + bucket.sample_count,
            )

    ordered = sorted(totals.items())
    page = ordered[:limit]
    total = sum((value[0] for _, value in ordered), Decimal(0))
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
        cursor=None,
        has_more=len(ordered) > limit,
        summary=ConsumptionSummary(
            total_volume_liters=float(total.quantize(Decimal("0.001"))),
            valid_interval_count=sum(value[1] for _, value in ordered),
        ),
    )


def empty_response(limit: int) -> ConsumptionResponse:
    return ConsumptionResponse(
        items=[],
        limit=limit,
        summary=ConsumptionSummary(total_volume_liters=0, valid_interval_count=0),
    )
