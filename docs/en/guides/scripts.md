---
title: Scripts and schedules
status: stable
translation_key: guides.scripts
source_revision: "2026-08-12"
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
