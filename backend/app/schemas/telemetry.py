from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TelemetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_serial: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=1, max_length=80)
    recorded_at: datetime
    cumulative_volume_liters: float | None = Field(default=None, ge=0, le=1_000_000_000)
    flow_rate_liters_minute: float | None = Field(default=None, ge=0, le=1_000_000)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    signal_dbm: int | None = Field(default=None, ge=-150, le=0)
    firmware_version: str | None = Field(default=None, max_length=40)

    @field_validator("device_serial", "event_id")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_volume_measurement(self) -> "TelemetryInput":
        if self.cumulative_volume_liters is None and self.flow_rate_liters_minute is None:
            raise ValueError("provide cumulative_volume_liters, flow_rate_liters_minute, or both")
        return self


class BatchTelemetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class TelemetryAccepted(BaseModel):
    reading_id: UUID | None
    event_id: str
    status: str
    duplicate: bool = False
    normalized_at: datetime | None = None
    code: str | None = None
    message: str | None = None


class BatchTelemetryOutput(BaseModel):
    items: list[TelemetryAccepted]
