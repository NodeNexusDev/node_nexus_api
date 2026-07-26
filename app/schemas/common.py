"""Common schemas for pagination and shared types."""

import base64
import json
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

T = TypeVar("T")


class CursorPage(BaseModel):
    """Cursor-based paginated response."""

    items: list
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = 20


def encode_cursor(created_at: datetime, id: UUID) -> str:
    """Encode a cursor from created_at and id."""
    if created_at.tzinfo:
        ts = created_at.isoformat()
    else:
        ts = created_at.replace(tzinfo=UTC).isoformat()
    payload = json.dumps({"ts": ts, "id": str(id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode a cursor into (created_at, id).

    Raises ValueError if the cursor is invalid.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor)
        data = json.loads(raw)
        return datetime.fromisoformat(data["ts"]), UUID(data["id"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc
