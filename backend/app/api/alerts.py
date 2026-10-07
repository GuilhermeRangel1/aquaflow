from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user
from app.db.models import Alert, AnomalyEvent, Property, User
from app.db.session import get_session
from app.schemas.alerts import AlertList, AlertOutput, AnomalyList, AnomalyOutput
from app.services.alerts import AlertNotFound, InvalidAlertTransition, transition_alert

router = APIRouter(tags=["anomalies and alerts"])
AlertStatus = Literal["open", "acknowledged", "resolved", "false_positive"]


@router.get("/api/v1/properties/{property_id}/anomalies", response_model=AnomalyList)
async def list_property_anomalies(
    property_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AnomalyList:
    property_exists = await session.scalar(
        select(Property.id).where(Property.id == property_id, Property.owner_id == user.id)
    )
    if property_exists is None:
        raise _not_found("property_not_found", "Property was not found")
    rows = list(
        (
            await session.scalars(
                select(AnomalyEvent)
                .where(AnomalyEvent.property_id == property_id)
                .order_by(AnomalyEvent.detected_at.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    page = rows[:limit]
    return AnomalyList(
        items=[_anomaly_output(item) for item in page],
        limit=limit,
        cursor=None,
        has_more=len(rows) > limit,
    )


@router.get("/api/v1/anomalies/{anomaly_id}", response_model=AnomalyOutput)
async def get_anomaly(
    anomaly_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AnomalyOutput:
    anomaly = await session.scalar(
        select(AnomalyEvent)
        .join(Property, Property.id == AnomalyEvent.property_id)
        .where(AnomalyEvent.id == anomaly_id, Property.owner_id == user.id)
    )
    if anomaly is None:
        raise _not_found("anomaly_not_found", "Anomaly was not found")
    return _anomaly_output(anomaly)


@router.get("/api/v1/properties/{property_id}/alerts", response_model=AlertList)
async def list_property_alerts(
    property_id: UUID,
    status: AlertStatus | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertList:
    property_exists = await session.scalar(
        select(Property.id).where(Property.id == property_id, Property.owner_id == user.id)
    )
    if property_exists is None:
        raise _not_found("property_not_found", "Property was not found")

    statement = (
        select(Alert, AnomalyEvent)
        .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
        .where(AnomalyEvent.property_id == property_id)
        .order_by(Alert.created_at.desc())
    )
    if status is not None:
        statement = statement.where(Alert.status == status)
    rows = list((await session.execute(statement.limit(limit + 1))).all())
    page = rows[:limit]
    return AlertList(
        items=[_to_output(alert, anomaly) for alert, anomaly in page],
        limit=limit,
        cursor=None,
        has_more=len(rows) > limit,
    )


@router.post("/api/v1/alerts/{alert_id}/acknowledge", response_model=AlertOutput)
async def acknowledge_alert(
    alert_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertOutput:
    return await _transition_alert(alert_id, "acknowledged", user, session)


@router.post("/api/v1/alerts/{alert_id}/resolve", response_model=AlertOutput)
async def resolve_alert(
    alert_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertOutput:
    return await _transition_alert(alert_id, "resolved", user, session)


@router.post("/api/v1/alerts/{alert_id}/false-positive", response_model=AlertOutput)
async def mark_alert_false_positive(
    alert_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertOutput:
    return await _transition_alert(alert_id, "false_positive", user, session)


async def _transition_alert(
    alert_id: UUID,
    target: Literal["acknowledged", "resolved", "false_positive"],
    user: User,
    session: AsyncSession,
) -> AlertOutput:
    try:
        alert, anomaly = await transition_alert(
            session,
            alert_id=alert_id,
            owner_id=user.id,
            target=target,
        )
    except AlertNotFound:
        raise _not_found("alert_not_found", "Alert was not found") from None
    except InvalidAlertTransition as error:
        raise _invalid_transition(error.current, error.target) from None
    return _to_output(alert, anomaly)


def _to_output(alert: Alert, anomaly: AnomalyEvent) -> AlertOutput:
    return AlertOutput(
        id=alert.id,
        anomaly_id=anomaly.id,
        property_id=anomaly.property_id,
        device_id=anomaly.device_id,
        detector_type=anomaly.detector_type,
        score=float(anomaly.score),
        severity=anomaly.severity,
        reason=anomaly.reason,
        window_start=anomaly.window_start,
        window_end=anomaly.window_end,
        evidence=anomaly.evidence,
        detected_at=anomaly.detected_at,
        status=alert.status,
        channel=alert.channel,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
    )


def _anomaly_output(anomaly: AnomalyEvent) -> AnomalyOutput:
    return AnomalyOutput(
        id=anomaly.id,
        property_id=anomaly.property_id,
        device_id=anomaly.device_id,
        detector_type=anomaly.detector_type,
        score=float(anomaly.score),
        severity=anomaly.severity,
        reason=anomaly.reason,
        window_start=anomaly.window_start,
        window_end=anomaly.window_end,
        evidence=anomaly.evidence,
        detected_at=anomaly.detected_at,
    )


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def _invalid_transition(current: str, target: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "invalid_alert_transition",
            "message": f"Cannot transition an alert from {current} to {target}",
        },
    )
