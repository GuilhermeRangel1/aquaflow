from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AlertOutput(BaseModel):
    id: UUID
    anomaly_id: UUID
    property_id: UUID
    device_id: UUID
    detector_type: str
    score: float = Field(ge=0, le=1)
    severity: Literal["low", "medium", "high"]
    reason: str
    window_start: datetime
    window_end: datetime
    evidence: dict[str, object]
    detected_at: datetime
    status: Literal["open", "acknowledged", "resolved", "false_positive"]
    channel: str
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class AlertList(BaseModel):
    items: list[AlertOutput]
    limit: int
    cursor: str | None = None
    has_more: bool = False


class AnomalyOutput(BaseModel):
    id: UUID
    property_id: UUID
    device_id: UUID
    detector_type: str
    score: float = Field(ge=0, le=1)
    severity: Literal["low", "medium", "high"]
    reason: str
    window_start: datetime
    window_end: datetime
    evidence: dict[str, object]
    detected_at: datetime


class AnomalyList(BaseModel):
    items: list[AnomalyOutput]
    limit: int
    cursor: str | None = None
    has_more: bool = False
