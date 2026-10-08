"""Allow devices to be retired without removing their telemetry history.

Revision ID: 0003_retire_devices
Revises: 0002_anomalies_alerts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_retire_devices"
down_revision: str | None = "0002_anomalies_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("devices", "is_active")
