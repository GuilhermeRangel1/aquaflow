import base64
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.security import hash_device_key
from app.db.models import Device, Property, TelemetryReading, User
from app.db.session import get_session
from app.schemas.resources import (
    DeviceCreate,
    DeviceHealthOutput,
    DeviceList,
    DeviceOutput,
    DevicePatch,
    DeviceReadingList,
    DeviceReadingOutput,
    PropertyCreate,
    PropertyList,
    PropertyOutput,
    PropertyPatch,
    ProvisionedDeviceOutput,
)

router = APIRouter(tags=["properties and devices"])


@router.get("/api/v1/properties", response_model=PropertyList)
async def list_properties(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> PropertyList:
    result = await session.scalars(
        select(Property).where(Property.owner_id == user.id).order_by(Property.created_at)
    )
    return PropertyList(items=[PropertyOutput.model_validate(item) for item in result])


@router.get("/api/v1/properties/{property_id}", response_model=PropertyOutput)
async def get_property(
    property_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PropertyOutput:
    property_row = await session.scalar(
        select(Property).where(Property.id == property_id, Property.owner_id == user.id)
    )
    if property_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "property_not_found", "message": "Property was not found"},
        )
    return PropertyOutput.model_validate(property_row)


@router.post("/api/v1/properties", status_code=201, response_model=PropertyOutput)
async def create_property(
    payload: PropertyCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PropertyOutput:
    property_row = Property(
        owner_id=user.id,
        name=payload.name,
        address=payload.address,
        timezone=payload.timezone,
        volume_unit=payload.volume_unit,
        notification_threshold_liters=payload.notification_threshold_liters,
        continuous_flow_threshold_liters_minute=payload.continuous_flow_threshold_liters_minute,
        continuous_flow_duration_minutes=payload.continuous_flow_duration_minutes,
        late_reading_window_days=7,
        created_at=datetime.now(UTC),
    )
    session.add(property_row)
    await session.commit()
    await session.refresh(property_row)
    return PropertyOutput.model_validate(property_row)


@router.patch("/api/v1/properties/{property_id}", response_model=PropertyOutput)
async def update_property(
    property_id: UUID,
    payload: PropertyPatch,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PropertyOutput:
    property_row = await session.scalar(
        select(Property).where(Property.id == property_id, Property.owner_id == user.id)
    )
    if property_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "property_not_found", "message": "Property was not found"},
        )
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(property_row, field_name, value)
    await session.commit()
    await session.refresh(property_row)
    return PropertyOutput.model_validate(property_row)


@router.get("/api/v1/devices", response_model=DeviceList)
async def list_devices(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> DeviceList:
    result = await session.scalars(
        select(Device)
        .join(Property, Device.property_id == Property.id)
        .where(Property.owner_id == user.id)
        .order_by(Device.created_at)
    )
    return DeviceList(items=[DeviceOutput.model_validate(item) for item in result])


async def _owned_device(session: AsyncSession, user: User, device_id: UUID) -> Device:
    device = await session.scalar(
        select(Device)
        .join(Property, Device.property_id == Property.id)
        .where(Device.id == device_id, Property.owner_id == user.id)
    )
    if device is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "device_not_found", "message": "Device was not found"},
        )
    return device


@router.get("/api/v1/devices/{device_id}", response_model=DeviceOutput)
async def get_device(
    device_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DeviceOutput:
    device = await _owned_device(session, user, device_id)
    return DeviceOutput.model_validate(device)


@router.patch("/api/v1/devices/{device_id}", response_model=DeviceOutput)
async def update_device(
    device_id: UUID,
    payload: DevicePatch,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DeviceOutput:
    device = await _owned_device(session, user, device_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, field_name, value)
    await session.commit()
    await session.refresh(device)
    return DeviceOutput.model_validate(device)


@router.get("/api/v1/devices/{device_id}/health", response_model=DeviceHealthOutput)
async def get_device_health(
    device_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DeviceHealthOutput:
    device = await _owned_device(session, user, device_id)
    latest = await session.scalar(
        select(TelemetryReading)
        .where(TelemetryReading.device_id == device.id)
        .order_by(TelemetryReading.recorded_at.desc(), TelemetryReading.received_at.desc())
        .limit(1)
    )
    now = datetime.now(UTC)
    last_seen = _as_utc(device.last_seen_at) if device.last_seen_at is not None else None
    seconds_since = max(0, int((now - last_seen).total_seconds())) if last_seen else None
    if last_seen is None:
        connectivity = "never_connected"
    elif seconds_since is not None and seconds_since <= device.expected_interval_seconds * 2:
        connectivity = "online"
    else:
        connectivity = "offline"
    return DeviceHealthOutput(
        device_id=device.id,
        connectivity=connectivity,
        last_seen_at=last_seen,
        seconds_since_last_seen=seconds_since,
        expected_interval_seconds=device.expected_interval_seconds,
        latest_reading=DeviceReadingOutput.model_validate(latest) if latest is not None else None,
    )


@router.get("/api/v1/devices/{device_id}/readings", response_model=DeviceReadingList)
async def list_device_readings(
    device_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DeviceReadingList:
    device = await _owned_device(session, user, device_id)
    if start is not None and (start.tzinfo is None or start.utcoffset() is None):
        raise HTTPException(
            status_code=422,
            detail={"code": "timezone_required", "message": "start must include a timezone"},
        )
    if end is not None and (end.tzinfo is None or end.utcoffset() is None):
        raise HTTPException(
            status_code=422,
            detail={"code": "timezone_required", "message": "end must include a timezone"},
        )
    start_utc = start.astimezone(UTC) if start is not None else None
    end_utc = end.astimezone(UTC) if end is not None else None
    if start_utc is not None and end_utc is not None and start_utc >= end_utc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_range", "message": "start must be before end"},
        )

    statement = select(TelemetryReading).where(TelemetryReading.device_id == device.id)
    if start_utc is not None:
        statement = statement.where(TelemetryReading.recorded_at >= start_utc)
    if end_utc is not None:
        statement = statement.where(TelemetryReading.recorded_at < end_utc)
    if cursor is not None:
        cursor_at, cursor_id = _decode_reading_cursor(cursor)
        statement = statement.where(
            or_(
                TelemetryReading.recorded_at < cursor_at,
                and_(
                    TelemetryReading.recorded_at == cursor_at,
                    TelemetryReading.id < cursor_id,
                ),
            )
        )
    readings = list(
        (
            await session.scalars(
                statement.order_by(
                    TelemetryReading.recorded_at.desc(), TelemetryReading.id.desc()
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(readings) > limit
    page = readings[:limit]
    next_cursor = _encode_reading_cursor(page[-1]) if has_more and page else None
    return DeviceReadingList(
        items=[DeviceReadingOutput.model_validate(reading) for reading in page],
        limit=limit,
        cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/api/v1/devices", status_code=201, response_model=ProvisionedDeviceOutput)
async def create_device(
    payload: DeviceCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ProvisionedDeviceOutput:
    property_row = await session.scalar(
        select(Property).where(Property.id == payload.property_id, Property.owner_id == user.id)
    )
    if property_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "property_not_found", "message": "Property was not found"},
        )
    device_key = f"af_{secrets.token_urlsafe(32)}"
    device = Device(
        property_id=property_row.id,
        serial_number=payload.serial_number,
        name=payload.name,
        expected_interval_seconds=payload.expected_interval_seconds,
        device_key_hash=hash_device_key(device_key),
        created_at=datetime.now(UTC),
    )
    try:
        session.add(device)
        await session.commit()
        await session.refresh(device)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "device_serial_already_registered",
                "message": "Device serial number already exists",
            },
        ) from None
    return ProvisionedDeviceOutput.model_validate(
        {**DeviceOutput.model_validate(device).model_dump(), "device_key": device_key}
    )


@router.post(
    "/api/v1/devices/{device_id}/rotate-key",
    response_model=ProvisionedDeviceOutput,
)
async def rotate_device_key(
    device_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ProvisionedDeviceOutput:
    device = await session.scalar(
        select(Device)
        .join(Property, Device.property_id == Property.id)
        .where(Device.id == device_id, Property.owner_id == user.id)
    )
    if device is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "device_not_found", "message": "Device was not found"},
        )

    device_key = f"af_{secrets.token_urlsafe(32)}"
    device.device_key_hash = hash_device_key(device_key)
    await session.commit()
    await session.refresh(device)
    return ProvisionedDeviceOutput.model_validate(
        {**DeviceOutput.model_validate(device).model_dump(), "device_key": device_key}
    )


def _encode_reading_cursor(reading: TelemetryReading) -> str:
    recorded_at = _as_utc(reading.recorded_at).isoformat()
    value = f"{recorded_at}|{reading.id}"
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_reading_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
        recorded_at_raw, reading_id_raw = decoded.rsplit("|", maxsplit=1)
        recorded_at = datetime.fromisoformat(recorded_at_raw)
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError("cursor timestamp must be timezone-aware")
        return recorded_at.astimezone(UTC), UUID(reading_id_raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_cursor", "message": "Reading cursor is invalid"},
        ) from None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
