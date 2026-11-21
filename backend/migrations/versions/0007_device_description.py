"""Add an optional description to each meter."""

import sqlalchemy as sa
from alembic import op

revision = "0007_device_description"
down_revision = "0006_telemetry_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("description", sa.String(240), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "description")
