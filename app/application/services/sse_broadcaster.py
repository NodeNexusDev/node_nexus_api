from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SseEvent:
    event: str
    data: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


class SseBroadcaster:
    """In-memory SSE event broadcaster."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[SseEvent | None]] = {}
        self._history: list[SseEvent] = []
        self._max_history = 100

    def subscribe(self) -> tuple[str, asyncio.Queue[SseEvent | None]]:
        sub_id = uuid.uuid4().hex
        queue: asyncio.Queue[SseEvent | None] = asyncio.Queue(maxsize=256)
        self._queues[sub_id] = queue
        for event in self._history[-50:]:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                break
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        self._queues.pop(sub_id, None)

    def publish(self, event: str, data: dict[str, Any]) -> None:
        sse_event = SseEvent(event=event, data=data)
        self._history.append(sse_event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        dead: list[str] = []
        for sub_id, queue in self._queues.items():
            try:
                queue.put_nowait(sse_event)
            except asyncio.QueueFull:
                dead.append(sub_id)
        for sub_id in dead:
            self._queues.pop(sub_id, None)

    @property
    def active_subscribers(self) -> int:
        return len(self._queues)


_broadcaster = SseBroadcaster()


def get_sse_broadcaster() -> SseBroadcaster:
    return _broadcaster
