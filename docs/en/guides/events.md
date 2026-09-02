---
title: SSE event stream
status: stable
translation_key: guides.events
source_revision: "2026-09-02"
---

# SSE event stream

Live server-sent events for node and execution lifecycle. Backed by `app/application/services/sse_broadcaster.py` (`SseBroadcaster`) and `app/api/v2/events.py`.

## Endpoint

```http
GET /api/v2/events/stream
Accept: text/event-stream
```

Requires authentication. Returns `StreamingResponse` with `text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`.

## Event format

```
: keepalive

id: 3fa85f64-5717-4562-b3fc-2c963f66afa6
event: node.status_changed
data: {"node_id": "...", "old_status": "online", "new_status": "offline"}

id: 3fa85f64-5717-4562-b3fc-2c963f66afa7
event: execution.completed
data: {"execution_id": "...", "exit_code": 0}
```

Keepalive `": keepalive"` is sent every 30s when idle (via `asyncio.wait_for(..., timeout=30)`).

## Event types

* `node.status_changed` — node connectivity changed (via `NodeStatusHistoryWriter`)
* `execution.completed` / `execution.failed` — command/script execution finished
* `script.scheduled` — schedule created or updated
* `job.progress` — long-running job progress (if emitted)

## Example

```bash
curl --fail-with-body -N \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/events/stream"
```

```javascript
// JavaScript EventSource
const es = new EventSource("/api/v2/events/stream", {
  headers: { "X-API-Key": token }
});
es.addEventListener("node.status_changed", e => console.log(JSON.parse(e.data)));
```

## Client handling

* Reconnect with `Last-Event-ID` is not yet persisted (in-memory `SseBroadcaster`).
* `broadcaster.subscribe()` returns `(sub_id, queue)`; queue size `128` (`_STREAM_QUEUE_SIZE`), `put_nowait` overflow removes dead subscriber.
* On disconnect `broadcaster.unsubscribe(sub_id)` is called in `finally`.

## See also

* `app/api/v2/events.py` — `_event_generator` and `event_stream`
* `app/application/services/sse_broadcaster.py` — in-memory pub/sub
* `dashboard-search-metrics.md` — overview with dashboard stats
