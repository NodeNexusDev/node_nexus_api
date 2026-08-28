"""Common schemas for pagination and shared types."""

import base64
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.core.types import JsonValue


class PaginatedResponse[T](BaseModel):
    """Paginated response with total count."""

    items: list[T]
    total: int
    page: int
    size: int


class CursorPage[T](BaseModel):
    """Cursor-based paginated response."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = 20


class ErrorResponse(BaseModel):
    """Unified error response schema."""

    code: str
    message: str
    request_id: str | None = None
    detail: JsonValue = None


AUTHENTICATED_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ErrorResponse,
        "description": "Authentication credentials are missing or invalid.",
    },
    403: {
        "model": ErrorResponse,
        "description": "The authenticated principal lacks the required permission.",
    },
    429: {
        "model": ErrorResponse,
        "description": "The configured request rate limit was exceeded.",
    },
    404: {
        "model": ErrorResponse,
        "description": "The requested resource was not found.",
    },
    409: {
        "model": ErrorResponse,
        "description": "The request conflicts with the current resource state.",
    },
    422: {
        "model": ErrorResponse,
        "description": "The request or a domain value failed validation.",
    },
    503: {
        "model": ErrorResponse,
        "description": "A required backend or remote service is unavailable.",
    },
}


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
