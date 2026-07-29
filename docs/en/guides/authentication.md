---
title: Authentication
status: stable
translation_key: guides.authentication
source_revision: "2026-07-29"
---

# Authentication

Node Nexus authenticates protected HTTP requests with the `X-API-Key` header.
Do not put a key in the query string: URLs are commonly retained in browser
history, access logs, and monitoring systems.

```bash
export NODE_NEXUS_URL=http://localhost:8000
export NODE_NEXUS_API_KEY='replace-with-your-key'

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

The master key configured through `MASTER_API_KEY` always has read-write access.
Managed keys support `read-only` and `read-write` scopes. A read-only key can
list and inspect resources but receives `403 Forbidden` for mutations.

| Status | Meaning | Action |
|---|---|---|
| `401` | The key is missing, unknown, inactive, or expired | Check the header and key lifecycle |
| `403` | The key is valid but lacks write scope | Use a read-write key only for mutations |
| `429` | The process-local rate limit was exceeded | Back off and retry after the current window |

Store keys in a secret manager or protected environment variable. Never commit,
log, or paste them into issue trackers. See [API key lifecycle](api-keys.md) for
creation, expiration, rotation, and revocation.
