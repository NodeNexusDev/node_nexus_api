---
title: Dashboard, search, and metrics
status: stable
translation_key: guides.dashboard-search-metrics
source_revision: "2026-08-17"
---

# Dashboard, search, and metrics

Stage E adds aggregated views, global search, execution statistics, and a
live event stream for monitoring.

## Dashboard overview

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/dashboard/"
```

Returns aggregated counts for nodes, Docker containers, scripts, commands,
and recent audit activity.

### Response fields

| Field | Description |
|-------|-------------|
| `nodes.total` | Total nodes |
| `nodes.active` | Nodes with status `active` |
| `nodes.unreachable` | Nodes with status `unreachable` |
| `docker.total` | Total Docker containers |
| `docker.running` | Running containers |
| `docker.stopped` | Stopped containers |
| `scripts.total` | Number of scripts |
| `commands.total` | Number of commands |
| `recent_activity` | Last 10 audit log entries |

## Dashboard metrics (time-series)

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/dashboard/metrics?group_by=day"
```

Returns time-bucketed execution metrics for charts. Parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `group_by` | `day` | Bucket granularity: `hour`, `day`, `week`, `month` |
| `date_from` | — | Start of range (ISO 8601) |
| `date_to` | — | End of range (ISO 8601) |

### Response

```json
{
  "command_metrics": [
    {
      "period": "2026-08-17 00:00:00+00:00",
      "total": 42,
      "successful": 38,
      "failed": 4,
      "cancelled": 0,
      "avg_duration_ms": 1250.5
    }
  ],
  "script_metrics": [...]
}
```

`date_from` is inclusive, `date_to` is exclusive (`[date_from, date_to)`). `avg_duration_ms` uses `GREATEST(0, finished_at - started_at)` and is `FILTER (WHERE finished_at IS NOT NULL)` for commands.

## Global search

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'q=deploy' \
  "${NODE_NEXUS_URL}/api/v2/search"
```

Searches across nodes, commands, scripts, and tags. Returns grouped results
by entity type.

## Execution statistics

### Command stats

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/stats"
```

### Script stats

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/stats"
```

### Command stats for a node

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=<node-id>"
```

Each stats endpoint returns `total`, `successful`, `failed`, `cancelled`, `success_rate` (`0..1`, `0.8 = 80%`, cancelled excluded), `avg_duration_ms`, `min_duration_ms`, `max_duration_ms`, and `last_executed_at`. Script `total` is terminal `success|error` (legacy `completed|failed`) only; `cancelled` is separate and not in `total`/`success_rate`; `pending`/`running` are excluded. `date_to` is exclusive.

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

Export audit log entries as JSON or CSV:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/export?fmt=csv"
```

Supported formats: `json` (default) and `csv`.
