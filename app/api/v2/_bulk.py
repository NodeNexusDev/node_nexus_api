"""Bulk helpers — 207 handling and result building."""

from __future__ import annotations

from fastapi import Response


def set_bulk_status(response: Response, succeeded: int, failed: int) -> None:
    """Set 207 Multi-Status when partially succeeded."""
    if failed > 0 and succeeded > 0:
        response.status_code = 207
