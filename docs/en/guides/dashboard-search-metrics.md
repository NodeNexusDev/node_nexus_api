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
  "${NODE_NEXUS_URL}/api/v1/dashboard/"
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
  "${NODE_NEXUS_URL}/api/v1/dashboard/metrics?group_by=day"
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
      "avg_duration_ms": 1250.5
    }
  ],
  "script_metrics": [...]
}
```

## Global search

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'q=deploy' \
  "${NODE_NEXUS_URL}/api/v1/search"
```

Searches across nodes, commands, scripts, and tags. Returns grouped results
by entity type.

## Execution statistics

### Command stats

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/commands/<command-id>/stats"
```

### Script stats

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script-id>/stats"
```

### Command stats for a node

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/commands/stats?node_id=<node-id>"
```

Each stats endpoint returns `total`, `successful`, `failed`, `success_rate`,
`avg_duration_ms`, `min_duration_ms`, `max_duration_ms`, and
`last_executed_at`. Script totals include terminal `success` and `error`
executions; `pending`, `running`, and `cancelled` executions are excluded.

## SSE event stream

Subscribe to live server-sent events:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/events/stream"
```

Events include `node.status_changed`, `execution.completed`,
`execution.failed`, `script.scheduled`, and `job.progress`.

## Audit export

Export audit log entries as JSON or CSV:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/audit/export?fmt=csv"
```

Supported formats: `json` (default) and `csv`.
