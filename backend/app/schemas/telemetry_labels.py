from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.resources import DeviceReadingOutput

TelemetryLabelValue = Literal["normal", "anomaly", "inconclusive", "ignored"]


class TelemetryLabelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: UUID
    reading_ids: list[UUID] = Field(min_length=1, max_length=100)
    label: TelemetryLabelValue
    notes: str = Field(min_length=3, max_length=1000)

    @field_validator("reading_ids")
    @classmethod
    def require_unique_readings(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("reading_ids must not contain duplicates")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("notes must contain at least three non-whitespace characters")
        return normalized


class TelemetryLabelOutput(BaseModel):
    id: UUID
    reading_id: UUID
    device_id: UUID
    label: TelemetryLabelValue
    notes: str
    reviewed_by_id: UUID
    reviewer_name: str
    reviewed_at: datetime


class TelemetryReviewItem(BaseModel):
    reading: DeviceReadingOutput
    current_label: TelemetryLabelOutput | None


class TelemetryReviewList(BaseModel):
    items: list[TelemetryReviewItem]
    limit: int
    cursor: str | None = None
    has_more: bool = False


class TelemetryLabelBatchOutput(BaseModel):
    items: list[TelemetryLabelOutput]


class TelemetryLabelHistory(BaseModel):
    items: list[TelemetryLabelOutput]
