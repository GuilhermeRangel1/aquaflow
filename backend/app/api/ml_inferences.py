from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.models import Device, MLInference, Property, TelemetryReading, User
from app.db.session import get_session
from app.schemas.ml_inferences import MLInferenceList, MLInferenceOutput

router = APIRouter(tags=["experimental ML inference"])


@router.get(
    "/api/v1/properties/{property_id}/ml-inferences",
    response_model=MLInferenceList,
)
async def list_property_ml_inferences(
    property_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MLInferenceList:
    property_exists = await session.scalar(
        select(Property.id).where(Property.id == property_id, Property.owner_id == user.id)
    )
    if property_exists is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "property_not_found", "message": "Property was not found"},
        )
    rows = (
        await session.execute(
            select(MLInference, TelemetryReading, Device)
            .join(TelemetryReading, TelemetryReading.id == MLInference.reading_id)
            .join(Device, Device.id == TelemetryReading.device_id)
            .where(Device.property_id == property_id)
            .order_by(MLInference.inferred_at.desc(), MLInference.id.desc())
            .limit(limit)
        )
    ).all()
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
            for inference, reading, device in rows
        ],
        limit=limit,
    )
