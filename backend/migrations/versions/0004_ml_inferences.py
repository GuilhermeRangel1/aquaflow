"""Persist versioned ML inferences separately from rule-based anomalies."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_ml_inferences"
down_revision: str | None = "0003_retire_devices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ml_inferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reading_id", sa.Uuid(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("predicted_anomaly", sa.Boolean(), nullable=True),
        sa.Column("anomaly_probability", sa.Numeric(8, 7), nullable=True),
        sa.Column("feature_values", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("inferred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reading_id"], ["telemetry_readings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reading_id", "model_version", name="uq_ml_inference_reading_model"),
    )

def downgrade() -> None:
    op.drop_table("ml_inferences")
