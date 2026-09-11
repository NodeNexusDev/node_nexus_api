"""Bulk helpers — 207 handling, BulkResponder and pagination offset helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import Response

from app.api.pagination import decode_offset, encode_offset
from app.schemas.common import BulkResult

HTTP_207_MULTI_STATUS: int = 207

# Re-export pagination helpers for bulk handlers that import from _bulk
__all__ = [
    "HTTP_207_MULTI_STATUS",
    "BulkResponder",
    "set_bulk_status",
    "execute_vert_bulk",
    "execute_vert_bulk_simple",
    "build_bulk_result",
    "pagination_offset_params",
    "pagination_cursor_next",
    "decode_offset",
    "encode_offset",
]

# Compatibility aliases for N816
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816


def set_bulk_status(response: Response, succeeded: int, failed: int) -> None:
    """Set 207 Multi-Status when partially succeeded."""
    if failed > 0 and succeeded > 0:
        response.status_code = HTTP_207_MULTI_STATUS


async def execute_vert_bulk[TItem, TResult](
    items: list[TItem],
    worker: Callable[[TItem], Awaitable[TResult]],
    response: Response,
) -> BulkResult[TResult]:
    """Execute vert bulk items concurrently and build BulkResult.

    Sets 207 when partially succeeded via ``set_bulk_status``.
    """
    return await execute_vert_bulk_simple(items, worker, response)


async def execute_vert_bulk_simple[TItem, TResult](
    items: list[TItem],
    worker: Callable[[TItem], Awaitable[TResult]],
    response: Response,
    *,
    success_status: str = "success",
) -> BulkResult[TResult]:
    """Variant for result types without strict status field checks."""
    sem = asyncio.Semaphore(20)

    async def _bounded(item: TItem) -> TResult:
        async with sem:
            return await worker(item)

    results = await asyncio.gather(*(_bounded(item) for item in items))
    succeeded = sum(1 for r in results if getattr(r, "status", None) == success_status)
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[TResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


# ---------------------------------------------------------------------------
# BulkResponder — centralized 207 handling
# ---------------------------------------------------------------------------


class _StatusCarrier(Protocol):
    status: str


def build_bulk_result[TResult](
    results: list[TResult],
    response: Response,
    *,
    success_status: str = "success",
) -> BulkResult[TResult]:
    """Build BulkResult and set 207 via response when partially succeeded."""
    succeeded = sum(1 for r in results if getattr(r, "status", None) == success_status)
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[TResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


class BulkResponder:
    """Helper to build BulkResult and set HTTP_207_MULTI_STATUS consistently."""

    def __init__(self, response: Response, *, success_status: str = "success") -> None:
        self.response = response
        self.success_status = success_status

    def result[TResult](self, results: list[TResult]) -> BulkResult[TResult]:
        """Build BulkResult using captured success_status and set 207."""
        return build_bulk_result(
            results, self.response, success_status=self.success_status
        )

    def status(self, succeeded: int, failed: int) -> None:
        """Directly apply 207 logic without building result."""
        set_bulk_status(self.response, succeeded, failed)


# ---------------------------------------------------------------------------
# Pagination offset helpers — DRY for cursor pagination
# ---------------------------------------------------------------------------


def pagination_offset_params(  # noqa: E501
    cursor: str | None, limit: int
) -> tuple[int, int, int, int]:
    """Parse cursor to offset and compute page/fetch/remainder.

    Raises HTTPException 422 on invalid cursor (via decode_offset).
    Returns (offset, page, fetch_size, remainder).
    """
    from fastapi import HTTPException

    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    remainder = offset % limit if limit else 0
    page = offset // limit + 1 if limit else 1
    fetch_size = limit + remainder if remainder else limit
    return offset, page, fetch_size, remainder


def pagination_cursor_next(  # noqa: E501
    offset: int, limit: int, total: int, returned: int
) -> tuple[str | None, bool]:
    """Compute next_cursor and has_more for cursor pagination."""
    has_more = (offset + returned) < total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return next_cursor, has_more
