from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


def add_audit_entry(
    session: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID,
    metadata: dict[str, object],
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            metadata_json=metadata,
            created_at=datetime.now(UTC),
        )
    )


def audit_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    return value
