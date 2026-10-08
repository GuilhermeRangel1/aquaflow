from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo")
    volume_unit: Mapped[str] = mapped_column(String(16), default="L")
    notification_threshold_liters: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    continuous_flow_threshold_liters_minute: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=Decimal("0.1")
    )
    continuous_flow_duration_minutes: Mapped[int] = mapped_column(Integer, default=360)
    late_reading_window_days: Mapped[int] = mapped_column(Integer, default=7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    property_id: Mapped[UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    serial_number: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    device_key_hash: Mapped[str] = mapped_column(String(64))
    expected_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    late_reading_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"
    __table_args__ = (UniqueConstraint("device_id", "event_id", name="uq_reading_device_event"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(80))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cumulative_volume_liters: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    flow_rate_liters_minute: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    quality: Mapped[str] = mapped_column(String(32), default="valid")
    battery_percent: Mapped[int | None] = mapped_column(Integer)
    signal_dbm: Mapped[int | None] = mapped_column(Integer)
    firmware_version: Mapped[str | None] = mapped_column(String(40))


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    property_id: Mapped[UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id"), index=True)
    detector_type: Mapped[str] = mapped_column(String(80))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 3))
    severity: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, object]] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("anomaly_id", name="uq_alert_anomaly"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    anomaly_id: Mapped[UUID] = mapped_column(ForeignKey("anomaly_events.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    channel: Mapped[str] = mapped_column(String(24), default="dashboard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(80), index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
