from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IngestionHealth(BaseModel):
    api_status: Literal["healthy"]
    readings_last_24h: int = Field(ge=0)
    last_reading_at: datetime | None
    mqtt_status: Literal["connected", "disconnected", "unavailable"]
    mqtt_messages_received: int = Field(ge=0)
    mqtt_messages_forwarded: int = Field(ge=0)
    mqtt_messages_rejected: int = Field(ge=0)
    mqtt_retries: int = Field(ge=0)
    mqtt_last_message_at: datetime | None


class ModelPipelineHealth(BaseModel):
    status: Literal["healthy", "degraded", "unavailable"]
    model_name: str | None = None
    model_version: str | None = None
    started_at: datetime | None = None
    last_check_at: datetime | None = None
    processed_records: int = Field(default=0, ge=0)
    failed_batches: int = Field(default=0, ge=0)
    scored_inferences_last_24h: int = Field(default=0, ge=0)
    skipped_inferences_last_24h: int = Field(default=0, ge=0)
    positive_predictions_last_24h: int = Field(default=0, ge=0)


class RuleFallbackHealth(BaseModel):
    status: Literal["active"]
    alerts_last_24h: int = Field(ge=0)
    explanation: str


class DashboardHealth(BaseModel):
    checked_at: datetime
    period_hours: Literal[24] = 24
    ingestion: IngestionHealth
    model_pipeline: ModelPipelineHealth
    rules_fallback: RuleFallbackHealth
