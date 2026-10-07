"""Add continuous-flow anomalies and dashboard alerts.

Revision ID: 0002_anomalies_alerts
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_anomalies_alerts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "continuous_flow_threshold_liters_minute",
            sa.Numeric(12, 3),
            server_default=sa.text("0.1"),
            nullable=False,
        ),
    )
    op.add_column(
        "properties",
        sa.Column(
            "continuous_flow_duration_minutes",
            sa.Integer(),
            server_default=sa.text("360"),
            nullable=False,
        ),
    )
    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("detector_type", sa.String(length=80), nullable=False),
        sa.Column("score", sa.Numeric(5, 3), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomaly_events_property_id", "anomaly_events", ["property_id"])
    op.create_index("ix_anomaly_events_device_id", "anomaly_events", ["device_id"])
    op.create_index(
        "ix_anomaly_property_detected",
        "anomaly_events",
        ["property_id", "detected_at"],
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anomaly_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="open", nullable=False),
        sa.Column("channel", sa.String(length=24), server_default="dashboard", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["anomaly_id"], ["anomaly_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anomaly_id", name="uq_alert_anomaly"),
    )
    op.create_index("ix_alerts_anomaly_id", "alerts", ["anomaly_id"])
    op.create_index("ix_alerts_status_created", "alerts", ["status", "created_at"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_resource_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_alerts_status_created", table_name="alerts")
    op.drop_index("ix_alerts_anomaly_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_anomaly_property_detected", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_device_id", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_property_id", table_name="anomaly_events")
    op.drop_table("anomaly_events")
    op.drop_column("properties", "continuous_flow_duration_minutes")
    op.drop_column("properties", "continuous_flow_threshold_liters_minute")
