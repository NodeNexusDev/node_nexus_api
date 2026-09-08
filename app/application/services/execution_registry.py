"""In-memory registry for background execution tasks."""

from __future__ import annotations

import asyncio
from uuid import UUID

_tasks: dict[UUID, asyncio.Task[None]] = {}


def register_execution(execution_id: UUID, task: asyncio.Task[None]) -> None:
    """Register a background execution task."""
    _tasks[execution_id] = task
    task.add_done_callback(lambda _: _tasks.pop(execution_id, None))


def get_execution_task(execution_id: UUID) -> asyncio.Task[None] | None:
    """Get a registered execution task."""
    return _tasks.get(execution_id)


def cancel_execution_task(execution_id: UUID) -> bool:
    """Cancel a registered execution task if exists."""
    task = _tasks.get(execution_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True
