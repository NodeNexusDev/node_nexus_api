---
title: Scripts and schedules
status: stable
translation_key: guides.scripts
source_revision: "2026-08-16"
---

# Scripts and schedules

A script is an ordered pipeline of inline commands and saved command templates.
Each step chooses `stop` or `continue` failure behavior. Execution can target
multiple nodes and produces per-node results.

Schedule definitions are stored in PostgreSQL and restored during startup.
`timezone` uses an IANA name and defaults to `UTC`; missed runs are coalesced,
each schedule has `max_instances=1`, and `misfire_grace_seconds` defaults to
60. APScheduler is only a runtime projection. Replicas coordinate execution
with a PostgreSQL advisory lock, so only one owner runs jobs at a time.

All target nodes are validated before execution. Nodes run with bounded
concurrency. History stores command fingerprints instead of rendered commands,
does not persist parameters, and truncates oversized output with byte counts.

## Search scripts

Add the `search` query parameter to filter by name or description:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'search=deploy' \
  "${NODE_NEXUS_URL}/api/v1/scripts/"
```

Search matches against the `name` and `description` fields using
case-insensitive comparison (ILIKE). The response returns only scripts whose
name or description contain the search substring.

## Global script tags

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/tags"
```

Returns a sorted list of unique tags used across all scripts. Useful for
building autocomplete and filter UIs.

## Execute by tags

A script can be executed on nodes filtered by tags instead of listing IDs.
The `node_ids` and `node_tags` parameters can be combined — the result is the
intersection (AND).

### Execute by IDs (as before)

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id-1>", "<node-id-2>"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script_id>/execute"
```

### Execute by tags

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_tags": ["web", "production"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script_id>/execute"
```

Runs on all nodes that have both tags `web` AND `production`.

### Mixed mode

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id>"], "node_tags": ["web"], "params": {}}' \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script_id>/execute"
```

The result is the intersection: nodes from `node_ids` that also have all
specified tags. At least one of `node_ids` or `node_tags` is required.

### Response

```json
{
  "script_id": "...",
  "total_nodes": 3,
  "results": [
    {"node_id": "...", "node_name": "web-1", "exit_code": 0, "stdout": "...", "stderr": ""},
    {"node_id": "...", "node_name": "web-2", "exit_code": 0, "stdout": "...", "stderr": ""}
  ]
}
```

Fields `exit_code`, `stdout`, `stderr` are present per step, but the batch
response `results` contains aggregated per-node data.

## Retry execution

Re-run a failed command or script execution with the same parameters.

### Retry a command execution

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/commands/${EXECUTION_ID}/retry"
```

### Retry a script execution

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/executions/${EXECUTION_ID}/retry"
```

Returns a new execution with the same `script_id`, `node_id`, and `params`.

## Cancel execution

Cancel a still-running script execution:

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/executions/${EXECUTION_ID}/cancel"
```

Only running executions can be cancelled. Already completed or failed executions
return an error.

## Schedule history

View the execution history of a specific schedule (cron-triggered runs):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/${SCRIPT_ID}/schedule/history?page=1&size=20"
```

Optional query: `trigger` — filter by trigger type (`manual`, `scheduled`,
`api`). Returns a paginated list of script executions with `trigger` and
`schedule_id` fields. Only executions created by `execute` or the scheduler are
included (command executions are not).
