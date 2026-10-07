from datetime import datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PropertyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    timezone: str = Field(default="America/Sao_Paulo", max_length=64)
    volume_unit: str = Field(default="L", pattern="^L$")
    notification_threshold_liters: Decimal | None = Field(
        default=None, gt=0, max_digits=14, decimal_places=3
    )
    continuous_flow_threshold_liters_minute: Decimal = Field(
        default=Decimal("0.1"), gt=0, max_digits=12, decimal_places=3
    )
    continuous_flow_duration_minutes: int = Field(default=360, ge=1, le=10080)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be a valid IANA timezone") from None
        return value


class PropertyOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: str | None
    timezone: str
    volume_unit: str
    notification_threshold_liters: Decimal | None
    continuous_flow_threshold_liters_minute: Decimal
    continuous_flow_duration_minutes: int
    late_reading_window_days: int
    created_at: datetime


class DeviceCreate(BaseModel):
    property_id: UUID
    serial_number: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    expected_interval_seconds: int = Field(default=300, ge=30, le=86400)

    @field_validator("serial_number", "name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class DeviceOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    property_id: UUID
    serial_number: str
    name: str
    expected_interval_seconds: int
    late_reading_window_days: int | None
    created_at: datetime | None
    last_seen_at: datetime | None


class ProvisionedDeviceOutput(DeviceOutput):
    device_key: str


class PropertyList(BaseModel):
    items: list[PropertyOutput]


class DeviceList(BaseModel):
    items: list[DeviceOutput]
