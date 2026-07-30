---
title: Manage nodes
status: stable
translation_key: guides.nodes
source_revision: "2026-07-30"
---

# Manage nodes

Nodes represent remote servers reachable over SSH. Each node stores an encrypted
credential, connectivity metadata, tags, and a last-checked status.

## Create a node

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v1/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "web-01",
    "host": "192.0.2.10",
    "port": 22,
    "connection_type": "ssh",
    "username": "ops",
    "password": "change-me",
    "tags": ["production", "frontend"]
  }'
```

Save the returned UUID for metrics, command execution, and connectivity checks.

## List and filter

Offset pagination:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'page=1' \
  --data-urlencode 'size=20' \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

Filter by tags with AND matching:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tags=production' \
  --data-urlencode 'tags=frontend' \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

Do not mix offset (`page`/`size`) and cursor (`cursor`/`limit`) pagination in
the same request. Use `total` from the response to iterate pages.

## Verify connectivity

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/check/"
```

A successful check confirms SSH reachability. The node status is updated
automatically.

## System metrics

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/metrics/"
```

Returns CPU, memory, disk, and load information from the remote host.

Use Swagger UI at `/docs` for the current request and response schemas.
