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


def parse_cursor_offset(cursor: str | None) -> int:
    """Parse cursor to offset, raising 422 on invalid."""
    if cursor is None or cursor == "":
        return 0
    try:
        return decode_offset(cursor)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid cursor") from None


def pagination_params(offset: int, limit: int) -> tuple[int, int, int]:
    """Translate offset/limit to page/fetch_size/remainder for offset-based services.

    Returns (page, fetch_size, remainder) where page is 1-based.
    """
    remainder = offset % limit if limit else 0
    page = offset // limit + 1 if limit else 1
    fetch_size = limit + remainder if remainder else limit
    return page, fetch_size, remainder


def cursor_next(  # noqa: E501
    offset: int, limit: int, total: int, returned: int
) -> tuple[str | None, bool]:
    """Build next_cursor and has_more from offset/limit/total."""
    has_more = (offset + returned) < total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return next_cursor, has_more
