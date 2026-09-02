"""Shared cursor pagination helpers (offset-based)."""

from __future__ import annotations

import base64
import json

from fastapi import HTTPException


def encode_offset(offset: int) -> str:
    """Encode an offset cursor for pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


def paginate_offset[T](
    items: list[T], cursor: str | None, limit: int
) -> tuple[list[T], str | None, bool]:
    """Slice items by offset cursor."""
    offset = 0
    if cursor is not None:
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    sliced = items[offset : offset + limit]
    has_more = (offset + len(sliced)) < len(items)
    next_cursor = encode_offset(offset + limit) if has_more else None
    return sliced, next_cursor, has_more
