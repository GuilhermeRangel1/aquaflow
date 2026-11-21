"""Store append-only, administrator-reviewed labels for telemetry readings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_telemetry_labels"
down_revision: str | None = "0005_archive_properties"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reading_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "label IN ('normal', 'anomaly', 'inconclusive', 'ignored')",
            name="ck_telemetry_label_value",
        ),
        sa.ForeignKeyConstraint(["reading_id"], ["telemetry_readings.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telemetry_labels_reading_id", "telemetry_labels", ["reading_id"])
    op.create_index("ix_telemetry_labels_reviewed_by_id", "telemetry_labels", ["reviewed_by_id"])
    op.create_index("ix_telemetry_labels_reviewed_at", "telemetry_labels", ["reviewed_at"])


def downgrade() -> None:
    op.drop_index("ix_telemetry_labels_reviewed_at", table_name="telemetry_labels")
    op.drop_index("ix_telemetry_labels_reviewed_by_id", table_name="telemetry_labels")
    op.drop_index("ix_telemetry_labels_reading_id", table_name="telemetry_labels")
    op.drop_table("telemetry_labels")
