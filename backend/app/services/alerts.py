from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, AnomalyEvent, AuditLog, Property

AlertAction = Literal["acknowledged", "resolved", "false_positive"]


class AlertNotFound(Exception):
    pass


class InvalidAlertTransition(Exception):
    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target


async def transition_alert(
    session: AsyncSession,
    *,
    alert_id: UUID,
    owner_id: UUID,
    target: AlertAction,
) -> tuple[Alert, AnomalyEvent]:
    result = await session.execute(
        select(Alert, AnomalyEvent)
        .join(AnomalyEvent, AnomalyEvent.id == Alert.anomaly_id)
        .join(Property, Property.id == AnomalyEvent.property_id)
        .where(Alert.id == alert_id, Property.owner_id == owner_id)
    )
    row = result.first()
    if row is None:
        raise AlertNotFound
    alert, anomaly = row

    if alert.status == target:
        return alert, anomaly
    if target == "acknowledged" and alert.status != "open":
        raise InvalidAlertTransition(alert.status, target)
    if target in {"resolved", "false_positive"} and alert.status not in {
        "open",
        "acknowledged",
    }:
        raise InvalidAlertTransition(alert.status, target)

    previous_status = alert.status
    now = datetime.now(UTC)
    alert.status = target
    if target == "acknowledged":
        alert.acknowledged_at = now
    else:
        alert.resolved_at = now
    session.add(
        AuditLog(
            actor_id=owner_id,
            action=f"alert.{target}",
            resource_type="alert",
            resource_id=str(alert.id),
            metadata_json={"from_status": previous_status, "to_status": target},
            created_at=now,
        )
    )
    await session.commit()
    await session.refresh(alert)
    return alert, anomaly
