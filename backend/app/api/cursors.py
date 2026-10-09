"""Opaque cursors for stable, timestamp-ordered API collections."""

import base64
from datetime import UTC, datetime
from uuid import UUID


def encode_time_id(timestamp: datetime, resource_id: UUID) -> str:
    timestamp = _as_utc(timestamp)
    value = f"{timestamp.isoformat()}|{resource_id}"
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def decode_time_id(cursor: str) -> tuple[datetime, UUID]:
    try:
        decoded = _decode(cursor)
        timestamp_raw, resource_id_raw = decoded.rsplit("|", maxsplit=1)
        timestamp = datetime.fromisoformat(timestamp_raw)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("cursor timestamp must include a timezone")
        return timestamp, UUID(resource_id_raw)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("cursor is invalid") from None


def encode_timestamp(timestamp: datetime) -> str:
    timestamp = _as_utc(timestamp)
    return (
        base64.urlsafe_b64encode(timestamp.isoformat().encode("utf-8")).decode("ascii").rstrip("=")
    )


def decode_timestamp(cursor: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(_decode(cursor))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("cursor timestamp must include a timezone")
        return timestamp
    except (ValueError, UnicodeDecodeError):
        raise ValueError("cursor is invalid") from None


def _decode(cursor: str) -> str:
    padded = cursor + "=" * (-len(cursor) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")


def _as_utc(timestamp: datetime) -> datetime:
    return timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp.astimezone(UTC)
