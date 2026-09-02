---
title: Audit log
status: stable
translation_key: guides.audit-log
source_revision: "2026-09-02"
---

# Audit log

The audit log records security-relevant and state-changing activity. Each entry
contains an action, timestamp, optional node, actor identifier, and details.
Treat it as operational evidence, not as a replacement for immutable external
security logging.

## Query events (cursor pagination)

Any valid key can list events with **cursor pagination** (`GET /audit/?cursor=&limit=2 → {items,next_cursor,has_more}`), not `page`/`size`/`total`. Iteration uses `has_more` + `next_cursor` — i.e., `{items, next_cursor, has_more, limit}` not `page`/`size`/`total`.

```bash
curl --get --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode "node_id=${NODE_ID}" \
  --data-urlencode 'action=execute_failed' \
  --data-urlencode 'cursor=eyJvZmZzZXQiOjIwfQ==' \
  --data-urlencode 'limit=2' \
  "${NODE_NEXUS_URL}/api/v2/audit/"
  # cursor=eyJvZmZzZXQiOjIwfQ== == {"offset":20} base64url
```

Response:

```json
{
  "items": [
    {"id": "...", "node_id": "...", "action": "execute_failed", "user": "admin", "details": "...", "created_at": "2026-09-02T10:00:00Z"}
  ],
  "next_cursor": "eyJvZmZzZXQiOjIyfQ==",
  "has_more": true,
  "limit": 2
}
```

Common actions include `create`, `update`, `delete`, `check`, `execute`, and
`execute_failed`. On the last page `next_cursor` is `null` and `has_more` is `false`. Invalid cursor → `422`.

Iterate:

```bash
  # page 1
curl --get --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?limit=50"
  # -> {items,next_cursor,has_more}
  # page 2
curl --get --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?cursor=<next_cursor>&limit=50"
```

### Filter by user and date

Additional query parameters allow filtering by user and date range (combine with `cursor`/`limit`/`node_id`/`action`):

```bash
curl --get --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'user=admin' \
  --data-urlencode 'date_from=2026-08-01T00:00:00' \
  --data-urlencode 'date_to=2026-08-16T23:59:59' \
  --data-urlencode 'limit=20' \
  "${NODE_NEXUS_URL}/api/v2/audit/"
```

Parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `user` | Filter by actor identifier | `user=admin` |
| `date_from` | Start of date range (ISO 8601) | `date_from=2026-08-01T00:00:00` |
| `date_to` | End of date range (ISO 8601) | `date_to=2026-08-31T23:59:59` |
| `cursor` | Opaque cursor (base64url JSON offset) | `cursor=eyJvZmZzZXQiOjIwfQ==` |
| `limit` | Page size 1..100 (default 20) | `limit=20` |

Filters can be combined with `node_id` and `action`. Legacy `page`/`size`/`total` no longer returned — use `has_more`/`next_cursor`.

## Stats

Aggregated audit statistics — `GET /audit/stats?group_by=hour|day|week|month` (snapshot `ExecutionStatsResponse` vs `MetricsBucket` semantics, audit uses `{bucket,count}`):

```bash
  # Explicit endpoint reference
  # GET /audit/stats
  # GET /audit/stats?group_by=hour|day|week|month
```

Detailed examples:

```bash
  # Snapshot (aggregate)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats"
  # -> {"total": 123, "buckets": []}

  # Buckets
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=day&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"
  # -> {"total": 123, "buckets": [{"bucket": "2026-09-01", "count": 42}, ...]}
  # or BulkResult buckets when group_by present: {"total":..., "succeeded":..., "failed":0, "results": [{"bucket","count"}]}

  # Supported group_by
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=hour"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=week"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=month"
```

`group_by` must be `hour`, `day`, `week`, or `month`. `date_from` inclusive, `date_to` exclusive.

## Export (CSV/JSON)

Export audit events for external analysis in JSON or CSV format with cursor pagination:

```bash
  # CSV (default)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=csv&limit=100"

  # JSON with cursor
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=json&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"

  # Legacy alias still documented as /audit/export?fmt=csv — use /audit/exports
```

Supported formats: `json` and `csv` (default `csv` in code). `limit` 1..100 (default 20), optional `cursor` (base64url offset). Filters `from_date`/`to_date`/`action`/`node_id` apply.

See [Dashboard, search, and metrics](dashboard-search-metrics.md) for the live
SSE event stream and unified execution statistics (`ExecutionStatsResponse` vs `StatsBucket`/`MetricsBucket`).

## Retention and deletion

At startup, the application removes entries older than
`AUDIT_LOG_RETENTION_DAYS`. Set the value to `0` to disable automatic cleanup,
then provide an external retention process if required.

Deleting the complete log is restricted to the master key and requires explicit
confirmation:

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${MASTER_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/?confirm=yes"
```

This operation is irreversible in the application database. Export or back up
required evidence first, restrict access to the master key, and record the
reason for deletion outside the log being removed.
