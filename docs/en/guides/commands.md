---
title: Reusable commands
status: stable
translation_key: guides.commands
source_revision: "2026-09-02"
---

# Reusable commands

Command templates define named parameters and can be tagged. Create the
template, execute it against a node with parameter values, and inspect each
result's exit code, stdout, and stderr. Parameters are validated before remote
execution; never build an untrusted shell fragment outside the template model.

## Create commands (bulk-first)

`POST /api/v2/commands/` is bulk-first without the `bulk` keyword. Send an
envelope `{items: [CommandCreate, ...]}` (1..20 items) and receive a `BulkResult`
with HTTP `201` when all succeed or `207 Multi-Status` on partial success.
Each `CommandCreate` carries `name`, `command` (with `{{ param }}` placeholders),
`parameters` (`{name, type:"string"|"integer"|"boolean", required, default, description}`),
`tags` (array), and `description`. Single creation is `items` with one element.

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/commands/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "name": "disk-usage",
        "command": "df -h {{ mount }}",
        "parameters": [{
          "name": "mount",
          "type": "string",
          "required": true,
          "description": "Absolute mount path"
        }],
        "tags": ["diagnostics"],
        "description": "Show disk usage"
      },
      {
        "name": "uptime",
        "command": "uptime",
        "parameters": [],
        "tags": ["diagnostics"]
      }
    ]
  }'
  # -> 201|207 {total,succeeded,failed,results:[{id?,name,status:"success"|"error",error}]}
```

`201` when `failed==0`, `207` when `succeeded>0 && failed>0`. Inspect each
`results[]` entry; successful templates are persisted, failed ones are not.

Legacy single-template `POST /commands` without `items` is no longer supported — wrap the template in `items`.

## List commands (cursor pagination)

Cursor pagination only (`COUNT(*)` removed). Use `cursor` + `limit` → `{items,next_cursor,has_more,limit}`. Supports `?tag=` (single tag) and `?search=` (ILIKE over `name`/`description`).

```bash
  # First page
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/?limit=20"

  # Next page
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"

  # Filter by tag and search
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tag=diagnostics' \
  --data-urlencode 'search=disk' \
  "${NODE_NEXUS_URL}/api/v2/commands/?limit=20"
  # -> {items:[{id,name,command,parameters,tags,description,created_at,updated_at}], next_cursor, has_more, limit}
```

The cursor encodes `{"offset": N}` as base64url JSON; `422` on invalid cursor. Iterate while `has_more` is true.

## Execute templates

### Single execution (legacy)

Save the returned UUID from bulk create, then execute against one node:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/execute" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d "{\"node_id\": \"${NODE_ID}\", \"params\": {\"mount\": \"/\"}}"
```

An `exit_code` of zero indicates success. Preserve `stderr` because utilities
can write warnings there. Parameters support `string`, `integer`, and `boolean`;
a missing required value fails before SSH execution.

### Bulk executions M×N (recommended)

Execute multiple commands on multiple nodes in one call (`M×N ≤100`). `207` on partial node/command failure.

```bash
  # M commands × N nodes — per-command params keyed by command_id string
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "command_ids": ["<cmd-1>", "<cmd-2>"],
    "node_ids": ["<node-1>", "<node-2>"],
    "node_tags": [],
    "params": {
      "<cmd-1>": {"mount": "/"},
      "<cmd-2>": {}
    }
  }'
  # -> {batch_id, total, succeeded, failed, results:[{command_id,command,node_id,node_name,stdout,stderr,exit_code,status:"success"|"error",error}]}
  # 200 all ok, 207 partial

  # With tag filtering (nodes resolved from node_ids ∩ node_tags; either can be empty but not both)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "command_ids": ["<cmd-1>"],
    "node_ids": [],
    "node_tags": ["production"],
    "params": {}
  }'
```

`M×N` guard: `len(command_ids) * max(len(node_ids), len(node_tags) or 1) ≤100`, else `422`.

### Raw executions M×N

Execute arbitrary command strings without a template (useful for ad-hoc ops):

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/raw-executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "commands": ["df -h /", "uptime"],
    "node_ids": ["<node-1>"],
    "node_tags": []
  }'
  # -> {batch_id, total, succeeded, failed, results:[{command,node_id,node_name,stdout,stderr,exit_code,status,error}]}
```

Same `M×N ≤100` guard and `207` handling.

## Retries and cancels (bulk)

Retries re-render the template (for `commands/executions`) and re-execute with the same node/params. Cancels abort still-running executions. Both are bulk-first (`207`) and accept an optional `?timeout=` query (1..600 seconds, default 30/60) to bound the wait.

```bash
  # Retry multiple command executions (with timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions/retries?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>", "<exec-2>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"retry_scheduled"|"error",message}]}

  # Cancel multiple command executions (with timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions/cancels?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"cancelled"|"error",message}]}
```

Single-execution retries (`POST /nodes/{id}/commands/{execution_id}/retry?timeout=30`) remain available for compatibility; prefer the bulk endpoints. Only `running` executions can be cancelled.

Execution history for a bulk batch:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/executions/history?batch_id=${BATCH_ID}&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # -> {items, next_cursor, has_more, limit} (CursorPage[CommandHistoryResponse])
```

Per-node history:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/history?node_id=${NODE_ID}&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

## Stats

Unified stats replace the old dashboard metrics. Without `group_by` the response is a snapshot `ExecutionStatsResponse`; with `group_by` it is `{buckets: [{period,total,successful,failed,cancelled,avg_duration_ms}]}`.

```bash
  # Snapshot — all commands
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats"
  # -> {total, successful, failed, cancelled, avg_duration_ms}

  # Snapshot filtered by node and date range
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=${NODE_ID}&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"

  # Buckets (grouped)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=${NODE_ID}&group_by=day"
  # -> {buckets:[{period,total,successful,failed,cancelled,avg_duration_ms}]}

  # Per-command snapshot and buckets
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/stats"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/stats?group_by=hour&date_from=2026-09-01T00:00:00Z"
  # -> {buckets:[...]} when group_by present
```

`group_by` accepts `hour|day|week|month`; `date_from`/`date_to` are ISO 8601 UTC.

## Search commands

Add the `search` query parameter to filter by name or description:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'search=disk' \
  "${NODE_NEXUS_URL}/api/v2/commands/"
```

Search matches against the `name` and `description` fields using
case-insensitive comparison (ILIKE). The response returns only templates whose
name or description contain the search substring.

## Global command tags

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/tags"
```

Returns a sorted list of unique tags used across all command templates. Useful
for building autocomplete and filter UIs.
