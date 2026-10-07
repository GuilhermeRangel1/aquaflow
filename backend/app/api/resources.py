import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.core.security import hash_device_key
from app.db.models import Device, Property, User
from app.db.session import get_session
from app.schemas.resources import (
    DeviceCreate,
    DeviceList,
    DeviceOutput,
    PropertyCreate,
    PropertyList,
    PropertyOutput,
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
        late_reading_window_days=7,
        created_at=datetime.now(UTC),
    )
    session.add(property_row)
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
