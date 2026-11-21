from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MLInferenceOutput(BaseModel):
    id: UUID
    reading_id: UUID
    event_id: str
    property_id: UUID
    device_id: UUID
    device_name: str
    recorded_at: datetime
    inferred_at: datetime
    model_version: str
    status: Literal["scored", "skipped"]
    predicted_anomaly: bool | None
    anomaly_probability: float | None = Field(default=None, ge=0, le=1)
    feature_values: dict[str, object]
    explanation: dict[str, object]
    reason: str


class MLInferenceList(BaseModel):
    items: list[MLInferenceOutput]
    limit: int
    cursor: str | None = None
    has_more: bool = False


class MeterAnalysis(BaseModel):
    reading_id: UUID
    recorded_at: datetime
    status: Literal["normal", "possible_anomaly", "insufficient_data"]
    alert_id: UUID | None = None


class MeterInferenceSummary(BaseModel):
    reading_id: UUID | None = None
    status: Literal["no_reading", "pending", "normal", "possible_anomaly", "insufficient_data"]
    latest_analysis: MeterAnalysis | None = None


class MeterRecentReading(BaseModel):
    reading_id: UUID
    recorded_at: datetime
    flow_rate_liters_minute: float | None
    status: Literal["pending", "normal", "possible_anomaly", "insufficient_data"]
    alert_id: UUID | None = None
