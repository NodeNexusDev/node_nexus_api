---
title: Observability
status: stable
translation_key: operations.observability
source_revision: "2026-08-17"
---

# Observability

Prometheus metrics are exposed at `PROMETHEUS_PATH` when enabled. OpenTelemetry
exports traces to `OTEL_ENDPOINT`. Structured logs cover request and lifecycle
events. Alert on readiness, error and timeout rates, latency, database failures,
and scheduler errors. Never collect API keys, SSH credentials, or private keys.

## Request correlation

Every request receives an `X-Request-ID` header in the response. You can send
your own `X-Request-ID` header and the API will echo it back. Error responses
for validation failures, HTTP exceptions, and domain errors include the same id
in the JSON body as `request_id`, making it easy to correlate client-side errors
with server logs.

## Metrics

Application metrics use the `node_nexus_` prefix. HTTP metrics are also exposed
by the default Prometheus FastAPI instrumentor using `method` and `handler`
labels. Audit outbox metrics report successful deliveries, failures, retries,
pending events, and the age of the oldest pending event. Scheduler metrics report
ownership, restoration readiness, registration failures, execution outcomes, and
execution duration. They also expose the active persistent schedule count,
misfires, overlap skips, and planned-to-observed start lag.

Alert on a growing `node_nexus_audit_pending` value, an increasing oldest
pending age, scheduler registration failures, and a scheduler readiness value
of zero. A non-owner replica normally reports `node_nexus_scheduler_owner 0`;
this alone is not a failure when another healthy replica owns the advisory lock.

## Dashboard

An aggregated system overview is available at `GET /api/v2/dashboard/`. The
endpoint returns statistics for nodes, Docker containers, scripts, commands,
and recent audit log activity.

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/dashboard/"
```

### Response

```json
{
  "nodes": {
    "total": 12,
    "active": 10,
    "unreachable": 2
  },
  "docker": {
    "total": 25,
    "running": 18,
    "stopped": 7
  },
  "scripts": {
    "total": 8
  },
  "commands": {
    "total": 15
  },
  "recent_activity": [
    {
      "id": "...",
      "action": "create",
      "node_id": "...",
      "user": "admin",
      "details": "{\"name\": \"web-1\"}",
      "created_at": "2026-08-16T10:00:00Z"
    }
  ]
}
```

### Fields

| Field | Description |
|-------|-------------|
| `nodes.total` | Total number of nodes |
| `nodes.active` | Nodes with status `active` |
| `nodes.unreachable` | Nodes with status `unreachable` |
| `docker.total` | Total Docker containers across all Docker nodes |
| `docker.running` | Running containers |
| `docker.stopped` | Stopped containers |
| `scripts.total` | Number of scripts |
| `commands.total` | Number of commands |
| `recent_activity` | Last 10 audit log entries |

Docker statistics are collected by running `docker ps -a` on each Docker node.
If a node is unreachable, its containers are not counted (errors are handled
gracefully).

## Dashboard metrics

Time-series execution metrics are available at `GET /api/v2/dashboard/metrics`.
Supports `hour`, `day`, `week`, and `month` bucket granularity with optional
`date_from` and `date_to` range filters. Returns command and script metrics
with `total`, `success`, `failure` counts per bucket.

## SSE event stream

Live server-sent events are available at `GET /api/v2/events/stream`. Events
include `node.status_changed`, `execution.completed`, `execution.failed`,
`script.scheduled`, and `job.progress`. Subscribe for real-time monitoring
without polling.

## Audit export

Audit log entries can be exported at `GET /api/v2/audit/export` with `fmt=json`
or `fmt=csv`. Use for external SIEM integration or compliance reporting.
