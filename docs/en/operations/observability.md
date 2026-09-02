---
title: Observability
status: stable
translation_key: operations.observability
source_revision: "2026-09-02"
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
in the JSON body as `request_id` (`string|null`), making it easy to correlate
client-side errors with server logs.

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

Prometheus exposure is unchanged in 2.0: `PROMETHEUS_ENABLED=true` exposes
metrics at `PROMETHEUS_PATH` (default `/metrics`), instrumentor excludes
`/health`, `/ready`, and the metrics path itself.

## Unified stats (replaces Dashboard)

> **Removed in 2.0:** `GET /api/v2/dashboard/` and `GET /api/v2/dashboard/metrics`
> were removed. Use unified stats endpoints described below. Docker statistics
> via `docker ps -a` on each Docker node are no longer aggregated there.

All stats now live under the entity (snapshot `ExecutionStatsResponse` without
`group_by`, bucketed `StatsBucket` / `StatsBucketsResponse` with `group_by`):

- `GET /api/v2/nodes/stats` (`GET /nodes/stats`) and `GET /api/v2/nodes/{id}/stats`
  — node execution stats
- `GET /api/v2/commands/stats?node_id=<uuid>` (`GET /commands/stats?node_id`) and
  `GET /api/v2/commands/{id}/stats` (`GET /commands/{id}/stats`) — command
  execution stats (filtered by node when `node_id` is present)
- `GET /api/v2/scripts/stats` and `GET /api/v2/scripts/{id}/stats` — script
  execution stats
- `GET /api/v2/audit/stats?group_by=hour|day|week|month`
  (`GET /audit/stats?group_by`) — audit stats (`?date_from`/`?date_to` range,
  `?group_by` bucketing; audit buckets are `{bucket,count}` and may return
  `BulkResult` when grouped)

Without `group_by` the endpoint returns a snapshot `ExecutionStatsResponse`:

```json
{
  "total": 42,
  "successful": 38,
  "failed": 4,
  "cancelled": 0,
  "success_rate": 0.904,
  "avg_duration_ms": 1250.5,
  "min_duration_ms": 80.0,
  "max_duration_ms": 5400.0,
  "last_executed_at": "2026-09-02T10:00:00Z"
}
```

With `group_by=hour|day|week|month` it returns bucketed stats
`{buckets:[{period,total,successful,failed,cancelled,avg_duration_ms}]}`.
For audit `GET /audit/stats?group_by=...` the bucket shape is `{bucket,count}`
and the aggregate is `{total, buckets:[{bucket,count}]}`; with `group_by` it can
also return `BulkResult`.

### Examples

```bash
  # Node stats — snapshot vs buckets
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/stats?group_by=day"

  # Command stats — snapshot
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/stats"

  # Command stats — filtered by node
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=<node-id>"

  # Audit stats — snapshot vs buckets
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=hour&date_from=2026-09-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"
```

Deployment smoke check (also see deployment guide):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?cursor=&limit=1"
```

## OpenAPI snapshot cache

`scripts/openapi.snapshot.json` caches the generated OpenAPI spec for fast E2E
coverage guards. Regenerate with `make generate-openapi` or
`uv run python scripts/generate_openapi_snapshot.py`. E2E tests
(`tests/e2e/test_endpoint_coverage_e2e.py`) use the cached snapshot if present;
otherwise the spec is generated on the fly.

## SSE event stream

Live server-sent events are available at `GET /api/v2/events/stream`. Events
include `node.status_changed`, `execution.completed`, `execution.failed`,
`script.scheduled`, and `job.progress`. Subscribe for real-time monitoring
without polling.

## Audit export

Audit log entries can be exported at `GET /api/v2/audit/exports` (cursor
pagination; legacy `GET /api/v2/audit/export?fmt=json|csv` still documented) with
`fmt=json` or `fmt=csv`. Use for external SIEM integration or compliance
reporting.
