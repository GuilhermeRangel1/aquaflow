from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cursors import decode_time_id, encode_time_id
from app.api.deps import current_user
from app.api.resources import _owned_device
from app.db.models import Alert, AnomalyEvent, Device, MLInference, Property, TelemetryReading, User
from app.db.session import get_session
from app.schemas.ml_inferences import (
    MeterAnalysis,
    MeterInferenceSummary,
    MeterRecentReading,
    MLInferenceList,
    MLInferenceOutput,
)

router = APIRouter(tags=["experimental ML inference"])


def _reading_status(
    inference: MLInference | None,
) -> Literal["pending", "normal", "possible_anomaly", "insufficient_data"]:
    if inference is None:
        return "pending"
    if inference.status != "scored" or inference.predicted_anomaly is None:
        return "insufficient_data"
    return "possible_anomaly" if inference.predicted_anomaly else "normal"


@router.get("/api/v1/devices/{device_id}/recent-analysis", response_model=list[MeterRecentReading])
async def get_recent_meter_analysis(
    device_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MeterRecentReading]:
    device = await _owned_device(session, user, device_id)
    latest_inference = (
        select(MLInference.id)
        .where(MLInference.reading_id == TelemetryReading.id)
        .order_by(MLInference.inferred_at.desc(), MLInference.id.desc())
        .limit(1)
        .correlate(TelemetryReading)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(TelemetryReading, MLInference)
            .outerjoin(MLInference, MLInference.id == latest_inference)
            .where(TelemetryReading.device_id == device.id)
            .order_by(TelemetryReading.recorded_at.desc(), TelemetryReading.id.desc())
            .limit(5)
        )
    ).all()
    pending_links = {
        str(inference.id)
        for _, inference in rows
        if inference is not None and _reading_status(inference) == "possible_anomaly"
    }
    links: dict[str, UUID] = {}
    if pending_links:
        alerts = await session.stream(
            select(Alert.id, AnomalyEvent.evidence)
            .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
            .where(
                AnomalyEvent.property_id == device.property_id,
                AnomalyEvent.device_id == device.id,
                AnomalyEvent.detector_type == "ml_anomaly",
                AnomalyEvent.window_start <= rows[0][0].recorded_at,
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
        )
        try:
            async for alert_id, evidence in alerts:
                matched = pending_links.intersection(evidence.get("ml_inference_ids") or [])
                links.update(dict.fromkeys(matched, alert_id))
                pending_links.difference_update(matched)
                if not pending_links:
                    break
        finally:
            await alerts.close()
    return [
        MeterRecentReading(
            reading_id=reading.id,
            recorded_at=reading.recorded_at
            if reading.recorded_at.tzinfo
            else reading.recorded_at.replace(tzinfo=UTC),
            flow_rate_liters_minute=float(reading.flow_rate_liters_minute)
            if reading.quality == "valid" and reading.flow_rate_liters_minute is not None
            else None,
            status=_reading_status(inference),
            alert_id=links.get(str(inference.id)) if inference else None,
        )
        for reading, inference in rows
    ]


@router.get(
    "/api/v1/devices/{device_id}/inference-summary",
    response_model=MeterInferenceSummary,
)
async def get_meter_inference_summary(
    device_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MeterInferenceSummary:
    device = await _owned_device(session, user, device_id)
    readings = select(TelemetryReading).where(TelemetryReading.device_id == device_id)
    latest = await session.scalar(
        readings.order_by(TelemetryReading.recorded_at.desc(), TelemetryReading.id.desc()).limit(1)
    )
    if latest is None:
        return MeterInferenceSummary(status="no_reading")

    row = (
        await session.execute(
            select(MLInference, TelemetryReading)
            .join(TelemetryReading, TelemetryReading.id == MLInference.reading_id)
            .where(
                TelemetryReading.device_id == device_id,
                TelemetryReading.recorded_at <= latest.recorded_at,
            )
            .order_by(
                TelemetryReading.recorded_at.desc(),
                (TelemetryReading.id == latest.id).desc(),
                MLInference.inferred_at.desc(),
                MLInference.id.desc(),
            )
            .limit(1)
        )
    ).first()
    if row is None:
        return MeterInferenceSummary(reading_id=latest.id, status="pending")

    inference, reading = row
    status = (
        "insufficient_data"
        if inference.status != "scored" or inference.predicted_anomaly is None
        else "possible_anomaly"
        if inference.predicted_anomaly
        else "normal"
    )
    alert_id = None
    if status == "possible_anomaly":
        alerts = await session.stream(
            select(Alert.id, AnomalyEvent.evidence)
            .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
            .where(
                AnomalyEvent.property_id == device.property_id,
                AnomalyEvent.device_id == device.id,
                AnomalyEvent.detector_type == "ml_anomaly",
                AnomalyEvent.window_start <= reading.recorded_at,
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
        )
        try:
            async for candidate_id, evidence in alerts:
                if str(inference.id) in (evidence.get("ml_inference_ids") or []):
                    alert_id = candidate_id
                    break
        finally:
            await alerts.close()
    return MeterInferenceSummary(
        reading_id=latest.id,
        status=status if reading.id == latest.id else "pending",
        latest_analysis=MeterAnalysis(
            reading_id=reading.id,
            recorded_at=reading.recorded_at.replace(tzinfo=UTC)
            if reading.recorded_at.tzinfo is None
            else reading.recorded_at,
            status=status,
            alert_id=alert_id,
        ),
    )


@router.get(
    "/api/v1/properties/{property_id}/ml-inferences",
    response_model=MLInferenceList,
)
async def list_property_ml_inferences(
    property_id: UUID,
    device_id: UUID | None = None,
    reading_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    latest_for_reading_ids: list[UUID] | None = Query(default=None, max_length=100),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MLInferenceList:
    property_exists = await session.scalar(
        select(Property.id).where(
            Property.id == property_id, Property.owner_id == user.id, Property.archived_at.is_(None)
        )
    )
    if property_exists is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "property_not_found", "message": "Property was not found"},
        )
    for name, value in (("start", start), ("end", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(
                status_code=422,
                detail={"code": "timezone_required", "message": f"{name} must include a timezone"},
            )
    start_utc = start.astimezone(UTC) if start is not None else None
    end_utc = end.astimezone(UTC) if end is not None else None
    if start_utc is not None and end_utc is not None and start_utc >= end_utc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_range", "message": "start must be before end"}
        )
    statement = (
        select(MLInference, TelemetryReading, Device)
        .join(TelemetryReading, TelemetryReading.id == MLInference.reading_id)
        .join(Device, Device.id == TelemetryReading.device_id)
        .where(Device.property_id == property_id)
    )
    if device_id is not None:
        statement = statement.where(Device.id == device_id)
    if reading_id is not None:
        statement = statement.where(TelemetryReading.id == reading_id)
    if latest_for_reading_ids is not None:
        latest_inference = (
            select(MLInference.id)
            .where(MLInference.reading_id == TelemetryReading.id)
            .order_by(MLInference.inferred_at.desc(), MLInference.id.desc())
            .limit(1)
            .correlate(TelemetryReading)
            .scalar_subquery()
        )
        statement = statement.where(
            TelemetryReading.id.in_(latest_for_reading_ids), MLInference.id == latest_inference
        )
    if start_utc is not None:
        statement = statement.where(TelemetryReading.recorded_at >= start_utc)
    if end_utc is not None:
        statement = statement.where(TelemetryReading.recorded_at < end_utc)
    if cursor is not None:
        try:
            cursor_at, cursor_id = decode_time_id(cursor)
        except ValueError:
            raise HTTPException(
                status_code=422, detail={"code": "invalid_cursor", "message": "Cursor is invalid"}
            ) from None
        statement = statement.where(
            or_(
                MLInference.inferred_at < cursor_at,
                and_(MLInference.inferred_at == cursor_at, MLInference.id < cursor_id),
            )
        )
    rows = (
        await session.execute(
            statement.order_by(MLInference.inferred_at.desc(), MLInference.id.desc()).limit(
                limit + 1
            )
        )
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    return MLInferenceList(
        items=[
            MLInferenceOutput(
                id=inference.id,
                reading_id=reading.id,
                event_id=reading.event_id,
                property_id=property_id,
                device_id=device.id,
                device_name=device.name,
                recorded_at=reading.recorded_at,
                inferred_at=inference.inferred_at,
                model_version=inference.model_version,
                status=inference.status,
                predicted_anomaly=inference.predicted_anomaly,
                anomaly_probability=(
                    float(inference.anomaly_probability)
                    if inference.anomaly_probability is not None
                    else None
                ),
                feature_values=inference.feature_values,
                explanation=inference.explanation,
                reason=inference.reason,
            )
            for inference, reading, device in page
        ],
        limit=limit,
        cursor=encode_time_id(page[-1][0].inferred_at, page[-1][0].id)
        if has_more and page
        else None,
        has_more=has_more,
    )
