---
title: Cheat sheet
status: stable
translation_key: reference.cheat-sheet
source_revision: "2026-08-16"
---

# Cheat sheet

Copy-paste recipes for common operations. Replace `${...}` placeholders
with your values.

## Setup

```bash
export NODE_NEXUS_URL=http://localhost:8000
export NODE_NEXUS_API_KEY='your-key'
```

## Nodes

| Task | Command |
|------|---------|
| List nodes | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/?page=1&size=20"` |
| List with tags | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/?tags=production&tags=frontend"` |
| Create node | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"srv","host":"192.0.2.10","port":22,"connection_type":"ssh","username":"ops","password":"...","tags":["prod"]}' "${NODE_NEXUS_URL}/api/v1/nodes/"` |
| Get one node | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Update node | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["prod","db"]}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Delete node | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Check connectivity | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/check/"` |
| Validate credentials | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"host":"192.0.2.10","port":22,"username":"ops","password":"..."}' "${NODE_NEXUS_URL}/api/v1/nodes/validate-credentials"` |
| Get metrics | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/metrics/"` |
| Status history | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/status-history?page=1&size=50"` |
| Bulk check | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v1/nodes/bulk/check"` |
| Bulk add tags | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>"],"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v1/nodes/bulk/tags/add"` |
| Bulk remove tags | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>"],"tags":["deprecated"]}' "${NODE_NEXUS_URL}/api/v1/nodes/bulk/tags/remove"` |
| Bulk delete | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v1/nodes/bulk/delete"` |

## Commands

| Task | Command |
|------|---------|
| Execute inline command | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"uptime"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/execute/"` |
| Execute on multiple nodes | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"df -h","node_ids":["id1","id2"]}' "${NODE_NEXUS_URL}/api/v1/nodes/bulk/execute/"` |
| Create command template | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"disk","command":"df -h {{ mount }}","parameters":[{"name":"mount","type":"string","required":true}]}' "${NODE_NEXUS_URL}/api/v1/commands/"` |
| List templates | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/commands/?page=1&size=20"` |
| Execute template | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d "{\"node_id\":\"${NODE_ID}\",\"params\":{\"mount\":\"/\"}}" "${NODE_NEXUS_URL}/api/v1/commands/${COMMAND_ID}/execute"` |
| Retry command | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/commands/${EXECUTION_ID}/retry"` |

## Docker

| Task | Command |
|------|---------|
| List containers | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/"` |
| List images | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/"` |
| Exec in container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec/"` |
| Start container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/start/"` |
| Stop container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stop/"` |

## Scripts

| Task | Command |
|------|---------|
| Retry script | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/scripts/executions/${EXECUTION_ID}/retry"` |
| Cancel execution | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/scripts/executions/${EXECUTION_ID}/cancel"` |
| Schedule history | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/scripts/${SCRIPT_ID}/schedule/history?page=1&size=20"` |

## Configuration

| Task | Command |
|------|---------|
| Export | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/config/export"` |
| Import | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v1/config/import"` |
| Dry-run import | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"dry_run":true,"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v1/config/import"` |

## API keys

| Task | Command |
|------|---------|
| Create key | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"reader","scope":"read-only"}' "${NODE_NEXUS_URL}/api/v1/api-keys/"` |
| List keys | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/api-keys/?page=1&size=20"` |
| Update key | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"is_active":false}' "${NODE_NEXUS_URL}/api/v1/api-keys/${KEY_ID}"` |
| Delete key | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/api-keys/${KEY_ID}"` |

## Audit

| Task | Command |
|------|---------|
| Query events | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/audit/?page=1&size=50"` |
| Filter by node | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/audit/?node_id=${NODE_ID}"` |
| Delete log | `curl -X DELETE -H "X-API-Key: ${MASTER_API_KEY}" "${NODE_NEXUS_URL}/api/v1/audit/?confirm=yes"` |

## Health

| Task | Command |
|------|---------|
| Liveness | `curl "${NODE_NEXUS_URL}/health"` |
| Readiness | `curl "${NODE_NEXUS_URL}/ready"` |
| Metrics | `curl "${NODE_NEXUS_URL}/metrics"` |

See the [HTTP API reference](api.md) for the complete endpoint catalog and
[interactive docs](openapi.html) for request/response schemas.
