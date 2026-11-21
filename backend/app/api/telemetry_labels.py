from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cursors import decode_time_id, encode_time_id
from app.api.deps import root_user
from app.db.models import Device, Property, TelemetryLabel, TelemetryReading, User
from app.db.session import get_session
from app.schemas.resources import DeviceReadingOutput
from app.schemas.telemetry_labels import (
    TelemetryLabelBatchOutput,
    TelemetryLabelCreate,
    TelemetryLabelHistory,
    TelemetryLabelOutput,
    TelemetryReviewItem,
    TelemetryReviewList,
)
from app.services.audit import add_audit_entry

router = APIRouter(tags=["telemetry labels"])


@router.get(
    "/api/v1/properties/{property_id}/telemetry-labels",
    response_model=TelemetryReviewList,
)
async def list_telemetry_for_review(
    property_id: UUID,
    device_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    user: User = Depends(root_user),
    session: AsyncSession = Depends(get_session),
) -> TelemetryReviewList:
    await _require_property(session, property_id, user)
    device = await session.scalar(
        select(Device).where(Device.id == device_id, Device.property_id == property_id)
    )
    if device is None:
        raise _not_found("device_not_found", "Device was not found")
    start_utc, end_utc = _time_range(start, end)

    latest_label_id = (
        select(TelemetryLabel.id)
        .where(TelemetryLabel.reading_id == TelemetryReading.id)
        .order_by(TelemetryLabel.reviewed_at.desc(), TelemetryLabel.id.desc())
        .limit(1)
        .correlate(TelemetryReading)
        .scalar_subquery()
    )
    statement = (
        select(TelemetryReading, TelemetryLabel, User)
        .outerjoin(TelemetryLabel, TelemetryLabel.id == latest_label_id)
        .outerjoin(User, User.id == TelemetryLabel.reviewed_by_id)
        .where(TelemetryReading.device_id == device.id)
    )
    if start_utc is not None:
        statement = statement.where(TelemetryReading.recorded_at >= start_utc)
    if end_utc is not None:
        statement = statement.where(TelemetryReading.recorded_at < end_utc)
    if cursor is not None:
        try:
            cursor_at, cursor_id = decode_time_id(cursor)
        except ValueError:
            raise _invalid_cursor() from None
        statement = statement.where(
            or_(
                TelemetryReading.recorded_at < cursor_at,
                and_(TelemetryReading.recorded_at == cursor_at, TelemetryReading.id < cursor_id),
            )
        )

    rows = (
        await session.execute(
            statement.order_by(
                TelemetryReading.recorded_at.desc(), TelemetryReading.id.desc()
            ).limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    return TelemetryReviewList(
        items=[
            TelemetryReviewItem(
                reading=_reading_output(reading),
                current_label=_label_output(reading, label, reviewer)
                if label is not None and reviewer is not None
                else None,
            )
            for reading, label, reviewer in page
        ],
        limit=limit,
        cursor=encode_time_id(page[-1][0].recorded_at, page[-1][0].id)
        if has_more and page
        else None,
        has_more=has_more,
    )


@router.post(
    "/api/v1/properties/{property_id}/telemetry-labels",
    status_code=201,
    response_model=TelemetryLabelBatchOutput,
)
async def label_telemetry_readings(
    property_id: UUID,
    payload: TelemetryLabelCreate,
    user: User = Depends(root_user),
    session: AsyncSession = Depends(get_session),
) -> TelemetryLabelBatchOutput:
    await _require_property(session, property_id, user)
    rows = list(
        (
            await session.execute(
                select(TelemetryReading, Device)
                .join(Device, Device.id == TelemetryReading.device_id)
                .where(
                    Device.property_id == property_id,
                    Device.id == payload.device_id,
                    TelemetryReading.id.in_(payload.reading_ids),
                )
                .order_by(TelemetryReading.id)
                .with_for_update(of=TelemetryReading)
            )
        ).all()
    )
    if len(rows) != len(payload.reading_ids):
        raise _not_found("readings_not_found", "One or more readings were not found")

    now = datetime.now(UTC)
    latest = await session.scalar(
        select(func.max(TelemetryLabel.reviewed_at)).where(
            TelemetryLabel.reading_id.in_(payload.reading_ids)
        )
    )
    if latest is not None:
        now = max(now, _as_utc(latest) + timedelta(microseconds=1))
    labels: list[TelemetryLabel] = []
    for reading, _device in rows:
        label = TelemetryLabel(
            reading_id=reading.id,
            label=payload.label,
            notes=payload.notes,
            reviewed_by_id=user.id,
            reviewed_at=now,
        )
        session.add(label)
        labels.append(label)
        add_audit_entry(
            session,
            actor_id=user.id,
            action="telemetry.label.recorded",
            resource_type="telemetry_reading",
            resource_id=reading.id,
            metadata={"label": payload.label},
        )
    await session.commit()

    return TelemetryLabelBatchOutput(
        items=[
            TelemetryLabelOutput(
                id=label.id,
                reading_id=reading.id,
                device_id=device.id,
                label=label.label,
                notes=label.notes,
                reviewed_by_id=user.id,
                reviewer_name=user.name,
                reviewed_at=now,
            )
            for (reading, device), label in zip(rows, labels, strict=True)
        ]
    )


@router.get(
    "/api/v1/properties/{property_id}/telemetry-labels/{reading_id}/history",
    response_model=TelemetryLabelHistory,
)
async def list_telemetry_label_history(
    property_id: UUID,
    reading_id: UUID,
    user: User = Depends(root_user),
    session: AsyncSession = Depends(get_session),
) -> TelemetryLabelHistory:
    await _require_property(session, property_id, user)
    reading = await session.scalar(
        select(TelemetryReading)
        .join(Device, Device.id == TelemetryReading.device_id)
        .where(TelemetryReading.id == reading_id, Device.property_id == property_id)
    )
    if reading is None:
        raise _not_found("reading_not_found", "Reading was not found")
    rows = (
        await session.execute(
            select(TelemetryLabel, User)
            .join(User, User.id == TelemetryLabel.reviewed_by_id)
            .where(TelemetryLabel.reading_id == reading.id)
            .order_by(TelemetryLabel.reviewed_at.desc(), TelemetryLabel.id.desc())
        )
    ).all()
    device = await session.get(Device, reading.device_id)
    assert device is not None
    return TelemetryLabelHistory(
        items=[
            TelemetryLabelOutput(
                id=label.id,
                reading_id=reading.id,
                device_id=device.id,
                label=label.label,
                notes=label.notes,
                reviewed_by_id=reviewer.id,
                reviewer_name=reviewer.name,
                reviewed_at=_as_utc(label.reviewed_at),
            )
            for label, reviewer in rows
        ]
    )


async def _require_property(session: AsyncSession, property_id: UUID, user: User) -> None:
    exists = await session.scalar(
        select(Property.id).where(
            Property.id == property_id,
            Property.owner_id == user.id,
            Property.archived_at.is_(None),
        )
    )
    if exists is None:
        raise _not_found("property_not_found", "Property was not found")


def _time_range(
    start: datetime | None, end: datetime | None
) -> tuple[datetime | None, datetime | None]:
    for name, value in (("start", start), ("end", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(
                status_code=422,
                detail={"code": "timezone_required", "message": f"{name} must include a timezone"},
            )
    start_utc = start.astimezone(UTC) if start is not None else None
    end_utc = end.astimezone(UTC) if end is not None else None
    if start_utc is not None and end_utc is not None and start_utc >= end_utc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_range", "message": "start must be before end"},
        )
    return start_utc, end_utc


def _reading_output(reading: TelemetryReading) -> DeviceReadingOutput:
    return DeviceReadingOutput(
        id=reading.id,
        event_id=reading.event_id,
        recorded_at=_as_utc(reading.recorded_at),
        received_at=_as_utc(reading.received_at),
        cumulative_volume_liters=reading.cumulative_volume_liters,
        flow_rate_liters_minute=reading.flow_rate_liters_minute,
        quality=reading.quality,
        battery_percent=reading.battery_percent,
        signal_dbm=reading.signal_dbm,
        firmware_version=reading.firmware_version,
    )


def _label_output(
    reading: TelemetryReading, label: TelemetryLabel, reviewer: User
) -> TelemetryLabelOutput:
    return TelemetryLabelOutput(
        id=label.id,
        reading_id=reading.id,
        device_id=reading.device_id,
        label=label.label,
        notes=label.notes,
        reviewed_by_id=reviewer.id,
        reviewer_name=reviewer.name,
        reviewed_at=_as_utc(label.reviewed_at),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def _invalid_cursor() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "invalid_cursor", "message": "Cursor is invalid"},
    )
