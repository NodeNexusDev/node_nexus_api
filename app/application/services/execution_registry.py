"""In-memory registry for background execution tasks."""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

_tasks: dict[UUID, tuple[asyncio.Task[None], float]] = {}
_TTL_SECONDS = 3600  # 1h expire for completed/cancelled tasks


def _cleanup_expired() -> None:
    now = time.monotonic()
    expired: list[UUID] = []
    for eid, entry in _tasks.items():
        if isinstance(entry, tuple):
            _, ts = entry
            if now - ts > _TTL_SECONDS:
                expired.append(eid)
        # legacy direct Task entries have no TTL, keep them
    for eid in expired:
        _tasks.pop(eid, None)


def register_execution(execution_id: UUID, task: asyncio.Task[None]) -> None:
    """Register a background execution task with TTL.

    Single-replica only: registry is in-memory and not shared across replicas.
    For multi-replica deployments, use Redis-backed registry (see middleware TODO).
    """
    _cleanup_expired()
    _tasks[execution_id] = (task, time.monotonic())
    task.add_done_callback(lambda _: _tasks.pop(execution_id, None))


def get_execution_task(execution_id: UUID) -> asyncio.Task[None] | None:
    """Get a registered execution task."""
    entry = _tasks.get(execution_id)
    if entry is None:
        return None
    # Support both tuple (new) and direct Task (legacy test direct assignment)
    if isinstance(entry, tuple):
        return entry[0]
    return entry  # type: ignore[return-value]


def cancel_execution_task(execution_id: UUID) -> bool:
    """Cancel a registered execution task if exists."""
    entry = _tasks.get(execution_id)
    if entry is None:
        return False
    task = entry[0] if isinstance(entry, tuple) else entry  # type: ignore[assignment]
    if task.done():
        return False
    task.cancel()
    return True
