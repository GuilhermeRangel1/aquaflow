from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ActiveModelSummary(BaseModel):
    key: str
    version: str
    trained_at: datetime | None
    threshold: float


class MLTrainingDashboardOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_model: ActiveModelSummary
    active_execution_id: str | None
    selected_execution_id: str | None
    history_available: bool
    worker_status: Literal["healthy", "degraded", "starting", "unavailable"]
    executions: list[dict[str, Any]]
    active_report: dict[str, Any]
    report: dict[str, Any]
