import asyncio
import json
from datetime import UTC, datetime, timedelta
from urllib.request import urlopen
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.models import Alert, AnomalyEvent, Device, MLInference, Property, TelemetryReading, User
from app.db.session import get_session
from app.schemas.dashboard_health import (
    DashboardHealth,
    IngestionHealth,
    ModelPipelineHealth,
    RuleFallbackHealth,
)

router = APIRouter(prefix="/api/v1/properties", tags=["dashboard health"])


def _read_health(url: str | None) -> dict[str, object] | None:
    if not url:
        return None
    try:
        with urlopen(url, timeout=1.5) as response:
            payload = json.loads(response.read())
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError):
        return None


@router.get("/{property_id}/dashboard-health", response_model=DashboardHealth)
async def get_dashboard_health(
    property_id: UUID,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DashboardHealth:
    property_exists = await session.scalar(
        select(Property.id).where(Property.id == property_id, Property.owner_id == user.id)
    )
    if property_exists is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "property_not_found", "message": "Property was not found"},
        )

    now = datetime.now(UTC)
    since = now - timedelta(hours=24)
    devices = select(Device.id).where(Device.property_id == property_id)
    readings_count = await session.scalar(
        select(func.count(TelemetryReading.id))
        .where(TelemetryReading.device_id.in_(devices), TelemetryReading.received_at >= since)
    )
    last_reading = await session.scalar(
        select(func.max(TelemetryReading.received_at)).where(
            TelemetryReading.device_id.in_(devices)
        )
    )

    inference_rows = (
        await session.execute(
            select(MLInference.status, MLInference.predicted_anomaly).join(
                TelemetryReading, TelemetryReading.id == MLInference.reading_id
            ).join(Device, Device.id == TelemetryReading.device_id).where(
                Device.property_id == property_id, MLInference.inferred_at >= since
            )
        )
    ).all()
    scored = sum(status == "scored" for status, _ in inference_rows)
    skipped = sum(status == "skipped" for status, _ in inference_rows)
    positives = sum(
        status == "scored" and prediction is True for status, prediction in inference_rows
    )
    latest_model_version = await session.scalar(
        select(MLInference.model_version)
        .join(TelemetryReading, TelemetryReading.id == MLInference.reading_id)
        .join(Device, Device.id == TelemetryReading.device_id)
        .where(Device.property_id == property_id)
        .order_by(MLInference.inferred_at.desc())
        .limit(1)
    )

    rule_alert_count = await session.scalar(
        select(func.count(Alert.id))
        .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
        .where(
            AnomalyEvent.property_id == property_id,
            AnomalyEvent.detector_type.in_(
                ["continuous_flow", "night_consumption", "device_offline"]
            ),
            Alert.created_at >= since,
        )
    )

    config = request.app.state.settings
    mqtt_data, worker_data = await asyncio.gather(
        asyncio.to_thread(_read_health, config.mqtt_ingestor_health_url),
        asyncio.to_thread(_read_health, config.ml_worker_health_url),
    )
    mqtt_connected = mqtt_data is not None and mqtt_data.get("status") == "connected"
    mqtt = IngestionHealth(
        api_status="healthy",
        readings_last_24h=readings_count or 0,
        last_reading_at=last_reading,
        mqtt_status=("connected" if mqtt_connected else "disconnected")
        if mqtt_data is not None
        else "unavailable",
        mqtt_messages_received=_nonnegative_int(mqtt_data, "messages_received"),
        mqtt_messages_forwarded=_nonnegative_int(mqtt_data, "messages_forwarded"),
        mqtt_messages_rejected=_nonnegative_int(mqtt_data, "messages_rejected"),
        mqtt_retries=_nonnegative_int(mqtt_data, "retries"),
        mqtt_last_message_at=_datetime(mqtt_data, "last_message_at"),
    )
    worker_status = worker_data.get("status") if worker_data else None
    pipeline = ModelPipelineHealth(
        status=worker_status if worker_status in {"healthy", "degraded"} else "unavailable",
        model_name=_string(worker_data, "model_name"),
        model_version=_string(worker_data, "model_version") or latest_model_version,
        started_at=_datetime(worker_data, "started_at"),
        last_check_at=_datetime(worker_data, "last_check_at"),
        processed_records=_nonnegative_int(worker_data, "processed_records"),
        failed_batches=_nonnegative_int(worker_data, "failed_batches"),
        scored_inferences_last_24h=scored,
        skipped_inferences_last_24h=skipped,
        positive_predictions_last_24h=positives,
    )
    # The rule detectors always operate independently; they are not conditional on ML failure.
    return DashboardHealth(
        checked_at=now,
        ingestion=mqtt,
        model_pipeline=pipeline,
        rules_fallback=RuleFallbackHealth(
            status="active",
            alerts_last_24h=rule_alert_count or 0,
            explanation=(
                "As regras continuam monitorando em paralelo, "
                "mesmo se o modelo estiver indisponível."
            ),
        ),
    )


def _nonnegative_int(data: dict[str, object] | None, key: str) -> int:
    value = data.get(key) if data else None
    return value if isinstance(value, int) and value >= 0 else 0


def _string(data: dict[str, object] | None, key: str) -> str | None:
    value = data.get(key) if data else None
    return value if isinstance(value, str) else None


def _datetime(data: dict[str, object] | None, key: str) -> datetime | None:
    value = _string(data, key)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
