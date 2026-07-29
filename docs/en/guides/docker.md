---
title: Manage remote Docker
status: stable
translation_key: guides.docker
source_revision: "2026-07-29"
---

# Manage remote Docker

Docker operations run through the node's SSH connection and require a reachable
Docker daemon on that host. Verify the node first, then list containers before
issuing state-changing operations. Bulk calls return individual results; a
partial failure does not roll back successful remote operations.

## Inspect before changing state

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers"
```

Use a returned container ID with `/start`, `/stop`, `/restart`, `/logs`,
`/stats`, or `/exec`. State-changing calls require a read-write key:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"command": "id", "timeout": 30}'
```

Identifiers, image names, and timeouts are validated before a remote command is
built. Still use a least-privilege SSH account and treat container execution as
privileged remote access. Bulk endpoints under `/api/v1/docker/bulk/` can
partially succeed; inspect every item in `results`.
