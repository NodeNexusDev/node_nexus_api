"""In-memory registry for background execution tasks."""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

_tasks: dict[UUID, tuple[asyncio.Task[None], float]] = {}
_TTL_SECONDS = 3600  # 1h expire for completed/cancelled tasks


def _cleanup_expired() -> None:
    now = time.monotonic()
    expired = [eid for eid, (_, ts) in _tasks.items() if now - ts > _TTL_SECONDS]
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
    return entry[0] if entry else None


def cancel_execution_task(execution_id: UUID) -> bool:
    """Cancel a registered execution task if exists."""
    entry = _tasks.get(execution_id)
    if entry is None:
        return False
    task = entry[0]
    if task.done():
        return False
    task.cancel()
    return True
