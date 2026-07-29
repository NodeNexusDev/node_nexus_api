---
title: Audit log
status: stable
translation_key: guides.audit-log
source_revision: "2026-07-29"
---

# Audit log

The audit log records security-relevant and state-changing activity. Each entry
contains an action, timestamp, optional node, actor identifier, and details.
Treat it as operational evidence, not as a replacement for immutable external
security logging.

## Query events

Any valid key can list events. Filter by node, action, or both:

```bash
curl --get --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode "node_id=${NODE_ID}" \
  --data-urlencode 'action=execute_failed' \
  --data-urlencode 'page=1' \
  --data-urlencode 'size=50' \
  "${NODE_NEXUS_URL}/api/v1/audit/"
```

Common actions include `create`, `update`, `delete`, `check`, `execute`, and
`execute_failed`. Use `total`, `page`, and `size` when iterating through results.

## Retention and deletion

At startup, the application removes entries older than
`AUDIT_LOG_RETENTION_DAYS`. Set the value to `0` to disable automatic cleanup,
then provide an external retention process if required.

Deleting the complete log is restricted to the master key and requires explicit
confirmation:

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${MASTER_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/audit/?confirm=yes"
```

This operation is irreversible in the application database. Export or back up
required evidence first, restrict access to the master key, and record the
reason for deletion outside the log being removed.
