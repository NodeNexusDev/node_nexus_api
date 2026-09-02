---
title: Scripts and schedules
status: stable
translation_key: guides.scripts
source_revision: "2026-09-02"
---

# Scripts and schedules

A script is an ordered pipeline of inline commands and saved command templates.
Each step chooses `stop` or `continue` failure behavior. A non-zero exit code
always marks the per-node result as `error`; `continue` only allows subsequent
steps to run. Execution can target multiple nodes and produces per-node results.

Schedule definitions are stored in PostgreSQL and restored during startup.
`timezone` uses an IANA name and defaults to `UTC`; missed runs are coalesced,
each schedule has `max_instances=1`, and `misfire_grace_seconds` defaults to
60. APScheduler is only a runtime projection. Replicas coordinate execution
with a PostgreSQL advisory lock, so only one owner runs jobs at a time.

All target nodes are validated before execution. Nodes run with bounded
concurrency. History stores command fingerprints instead of rendered commands,
does not persist parameters, and truncates oversized output with byte counts.

## Create scripts (bulk-first)

`POST /api/v2/scripts/` is bulk-first without the `bulk` keyword. Send an
envelope `{items: [ScriptCreate, ...]}` (1..20 items) and receive a `BulkResult`
with `201` when all succeed or `207 Multi-Status` on partial success. Each
`ScriptCreate` carries `name`, `description`, `steps` (array of `{label, type:"command"|"command_id", command?, command_id?, params?, on_failure:"stop"|"continue"}`), and `tags`. Single creation is `items` with one element.

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/scripts/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "name": "deploy",
        "description": "Deploy main branch",
        "tags": ["deploy"],
        "steps": [
          {"label": "pull", "type": "command", "command": "git pull", "params": {}, "on_failure": "stop"},
          {"label": "restart", "type": "command_id", "command_id": "<command-uuid>", "params": {"branch": "main"}, "on_failure": "stop"}
        ]
      }
    ]
  }'
  # -> 201|207 {total,succeeded,failed,results:[{id?,name,status:"success"|"error",error}]}
```

`201` when `failed==0`, `207` when `succeeded>0 && failed>0`. Inspect `results[]`.

## List scripts (cursor pagination)

Cursor pagination only. Use `cursor` + `limit` → `{items,next_cursor,has_more,limit}`. Supports `?tag=` (single tag) and `?search=` (ILIKE over `name`/`description`).

```bash
  # First page
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/?limit=20"

  # Next page
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"

  # Filter by tag and search
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tag=deploy' \
  --data-urlencode 'search=deploy' \
  "${NODE_NEXUS_URL}/api/v2/scripts/?limit=20&tag=deploy&search=deploy"
  # -> {items:[{id,name,description,steps,tags,created_at,updated_at}], next_cursor, has_more, limit}
```

Cursor encodes `{"offset": N}` as base64url JSON; `422` on invalid cursor. Iterate while `has_more` is true. `search` matches `name` and `description` (ILIKE).

## Global script tags

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/tags"
```

Returns a sorted list of unique tags used across all scripts. Useful for
building autocomplete and filter UIs.

## Execute scripts

### Single execution (per script)

A script can be executed on nodes filtered by IDs and/or tags (intersection AND). At least one of `node_ids` or `node_tags` is required.

```bash
  # By IDs
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id-1>", "<node-id-2>"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script_id>/execute"

  # By tags (all nodes that have both tags)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_tags": ["web", "production"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script_id>/execute"

  # Mixed (intersection: nodes from node_ids that also have tags)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id>"], "node_tags": ["web"], "params": {}}' \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script_id>/execute"
  # -> {script_id, total_nodes, results:[{node_id, node_name, exit_code, stdout, stderr}]}
```

Per-step `exit_code`, `stdout`, `stderr` are present inside `steps` of `GET /scripts/{id}/executions` history; the `execute` response aggregates per node.

### Bulk executions M×N (recommended)

Execute multiple scripts on multiple nodes in one call (`M×N ≤100`) with `207` handling.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "script_ids": ["<script-1>", "<script-2>"],
    "node_ids": ["<node-1>", "<node-2>"],
    "node_tags": [],
    "params": {
      "<script-1>": {"branch": "main"},
      "<script-2>": {}
    }
  }'
  # -> {batch_id, total, succeeded, failed, results:[{script_id,execution_id,node_id,node_name,status:"success"|"error",steps:[{step_index,label,command_fingerprint,stdout,stderr,stdout_bytes,stderr_bytes,truncated,exit_code}],error}]}
  # 200 all ok, 207 partial

  # With tag filtering
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "script_ids": ["<script-1>"],
    "node_ids": [],
    "node_tags": ["production"],
    "params": {}
  }'
```

`M×N` guard: `len(script_ids) * max(len(node_ids), len(node_tags) or 1) ≤100`, else `422`. Inspect `results[]` per `status`; partial failures do not roll back successful executions.

Execution history for a script (cursor pagination):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/executions?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # -> {items:[{id, script_id, node_id, params, status, steps:[...], started_at, finished_at}], next_cursor, has_more, limit}
```

## Retries and cancels (bulk)

Retries re-execute with the same `script_id`, `node_id`, and `params`. Cancels abort still-running executions. Both are bulk-first with `207` and accept an optional `?timeout=` query (1..600 seconds, default 30/60) to bound the wait.

```bash
  # Bulk retry executions (with timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions/retries?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>", "<exec-2>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"retry_scheduled"|"error",message}]}

  # Bulk cancel executions (with timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions/cancels?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"cancelled"|"error",message}]}
```

Single-execution compat endpoints also exist (`POST /scripts/executions/{id}/retry?timeout=30`, `/cancel?timeout=30` and `POST /nodes/{id}/commands/{id}/retry` for commands) but prefer bulk. Only `running` executions can be cancelled.

## Stats

Unified stats without `group_by` return a snapshot `ExecutionStatsResponse`; with `group_by` return `{buckets: [{period,total,successful,failed,cancelled,avg_duration_ms}]}`.

```bash
  # Snapshot — all scripts
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/stats"
  # -> {total, successful, failed, cancelled, avg_duration_ms}

  # Snapshot filtered by node and date range
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/stats?node_id=${NODE_ID}&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"

  # Buckets (grouped)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/stats?node_id=${NODE_ID}&group_by=day"
  # -> {buckets:[{period,total,successful,failed,cancelled,avg_duration_ms}]}

  # Per-script snapshot and buckets
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/stats"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/stats?group_by=hour&date_from=2026-09-01T00:00:00Z"
  # -> {buckets:[...]} when group_by present
```

`group_by` accepts `hour|day|week|month`; `date_from`/`date_to` are ISO 8601 UTC.

## Schedule history

View the execution history of a specific schedule (cron-triggered runs):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/schedule/history?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # cursor pagination (CursorPage[ScriptExecutionResponse])
```

Optional query: `trigger` — filter by trigger type (`manual`, `scheduled`,
`api`). Returns a cursor-paginated list of script executions with `trigger` and
`schedule_id` fields. Only executions created by `execute` or the scheduler are
included (command executions are not). Legacy `?page`/`size` alias is no longer the canonical pagination for schedules — use `cursor`/`limit`.
