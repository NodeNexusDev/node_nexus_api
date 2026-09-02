"""Bulk helpers — 207 handling and vert bulk execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import Response

from app.schemas.common import BulkResult


def set_bulk_status(response: Response, succeeded: int, failed: int) -> None:
    """Set 207 Multi-Status when partially succeeded."""
    if failed > 0 and succeeded > 0:
        response.status_code = 207


async def execute_vert_bulk[TItem, TResult](
    items: list[TItem],
    worker: Callable[[TItem], Awaitable[TResult]],
    response: Response,
) -> BulkResult[TResult]:
    """Execute vert bulk items concurrently and build BulkResult.

    Sets 207 when partially succeeded via ``set_bulk_status``.
    """
    results = await asyncio.gather(*(worker(item) for item in items))
    succeeded = sum(1 for r in results if getattr(r, "status", None) == "success")
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[TResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


async def execute_vert_bulk_simple[TItem, TResult](
    items: list[TItem],
    worker: Callable[[TItem], Awaitable[TResult]],
    response: Response,
    *,
    success_status: str = "success",
) -> BulkResult[TResult]:
    """Variant for result types without strict status field checks."""
    results = await asyncio.gather(*(worker(item) for item in items))
    succeeded = sum(1 for r in results if getattr(r, "status", None) == success_status)
    failed = len(results) - succeeded
    set_bulk_status(response, succeeded, failed)
    return BulkResult[TResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )
