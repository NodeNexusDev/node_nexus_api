"""SSE event stream endpoint."""

import asyncio
import json

import structlog
from dishka.integrations.fastapi import DishkaRoute, inject
from fastapi import APIRouter, Security
from fastapi.responses import StreamingResponse

from app.api.deps import Principal, get_current_principal
from app.application.services.sse_broadcaster import get_sse_broadcaster

audit = structlog.get_logger("audit")

router = APIRouter(tags=["events"], route_class=DishkaRoute)


async def _event_generator(sub_id: str, queue):
    broadcaster = get_sse_broadcaster()
    try:
        yield ":\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                break
            payload = json.dumps(event.data, default=str)
            yield f"id: {event.id}\nevent: {event.event}\ndata: {payload}\n\n"
    finally:
        broadcaster.unsubscribe(sub_id)


@router.get("/events/stream")
@inject
async def event_stream(
    _key: Principal = Security(get_current_principal),
) -> StreamingResponse:
    """Subscribe to live server-sent events.

    Events: node.status_changed, execution.completed, execution.failed,
    script.scheduled, job.progress.
    """
    audit.info("api.events.stream.connect")
    broadcaster = get_sse_broadcaster()
    sub_id, queue = broadcaster.subscribe()
    return StreamingResponse(
        _event_generator(sub_id, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
