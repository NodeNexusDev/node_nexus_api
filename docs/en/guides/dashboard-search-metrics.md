---
title: Dashboard, search, and metrics
status: stable
translation_key: guides.dashboard-search-metrics
source_revision: "2026-09-02"
---

# Dashboard, search, and metrics

Stage E adds aggregated views, global search, execution statistics, and a
live event stream for monitoring.

> **Dashboard removed in 2.0:** `GET /api/v2/dashboard/` and `GET /api/v2/dashboard/metrics` were removed. Use unified stats endpoints (`GET /.../stats`) described below — snapshot `ExecutionStatsResponse` without `group_by`, buckets with `group_by=hour|day|week|month`.

## Unified stats (replaces Dashboard)

All stats now live under the entity (unified `ExecutionStatsResponse` vs `MetricsBucket`/`StatsBucket`):

- `GET /api/v2/commands/stats` — aggregated command executions (optional `?node_id=<uuid>`) — also `GET /commands/stats?node_id`
- `GET /api/v2/commands/{id}/stats` — per-command execution stats — `GET /commands/{id}/stats`
- `GET /api/v2/scripts/stats` and `GET /api/v2/scripts/{id}/stats` — script execution stats
- `GET /api/v2/nodes/stats` and `GET /api/v2/nodes/{id}/stats` — node execution stats — `GET /nodes/stats`, `GET /nodes/{id}/stats`
- `GET /api/v2/audit/stats` — audit stats (`?group_by=hour|day|week|month`, `?date_from`/`?date_to`) — `GET /audit/stats?group_by=hour|day|week|month`

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

`success_rate` is `0..1` (`0.8 = 80%`, `cancelled` excluded from `total`/`success_rate`). Script `total` counts only terminal `success|error` (legacy `completed|failed`); `cancelled` is separate and `pending`/`running` are excluded. `date_to` is exclusive (`[date_from, date_to)`), `avg_duration_ms` uses `GREATEST(0, finished_at - started_at)` `FILTER (WHERE finished_at IS NOT NULL)`.

With `group_by` the endpoint returns buckets (`{buckets: MetricsBucket[]}` / `StatsBucketsResponse`):

```json
{
  "buckets": [
    {
      "period": "2026-09-02 00:00:00+00:00",
      "total": 42,
      "successful": 38,
      "failed": 4,
      "cancelled": 0,
      "avg_duration_ms": 1250.5
    }
  ]
}
```

For audit `GET /audit/stats?group_by=...` the bucket shape is `{bucket, count}` and the aggregate is `{total, buckets:[{bucket,count}]}`; with `group_by` it can also return `BulkResult` buckets.

### Examples

```bash
  # Command stats — snapshot
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/stats"

  # Command stats — buckets by day
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/stats?group_by=day&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"

  # Command stats for a node (snapshot)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=<node-id>"

  # Command stats for a node — buckets
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=<node-id>&group_by=week"

  # Nodes stats — snapshot vs buckets
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/stats?group_by=day"

  # Audit stats — snapshot vs buckets
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=hour&date_from=2026-09-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"
```

`group_by` must be `hour`, `day`, `week`, or `month`. `date_from` is inclusive, `date_to` exclusive.

## Global search

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'q=deploy' \
  "${NODE_NEXUS_URL}/api/v2/search"
```

Searches across nodes, commands, scripts, and tags. Returns grouped results
by entity type.

## Execution statistics (legacy detail preserved)

See unified stats above. Each `ExecutionStatsResponse` returns `total`, `successful`, `failed`, `cancelled`, `success_rate` (`0..1`, `0.8 = 80%`, cancelled excluded), `avg_duration_ms`, `min_duration_ms`, `max_duration_ms`, and `last_executed_at`. Script `total` is terminal `success|error` (legacy `completed|failed`) only; `cancelled` is separate and not in `total`/`success_rate`; `pending`/`running` are excluded. `date_to` is exclusive.

## SSE event stream

Subscribe to live server-sent events:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/events/stream"
```

Events include `node.status_changed`, `execution.completed`,
`execution.failed`, `script.scheduled`, and `job.progress`.

## Audit export

Export audit log entries as JSON or CSV (now under `GET /audit/exports` with cursor pagination; legacy `?fmt=csv` still documented):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=csv&limit=100"
  # or ?fmt=json
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=json&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

Supported formats: `json` (default) and `csv`. See [Audit log](audit-log.md) for cursor-paginated listing and `GET /audit/stats`.
