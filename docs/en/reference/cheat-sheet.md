---
title: Cheat sheet
status: stable
translation_key: reference.cheat-sheet
source_revision: "2026-08-25"
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
| Create node (SSH key) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"srv","host":"192.0.2.10","port":22,"connection_type":"ssh","username":"ops","ssh_key":"<key>","passphrase":"<pass>"}' "${NODE_NEXUS_URL}/api/v1/nodes/"` |
| Get one node | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Update node | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["prod","db"]}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Delete node | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Check connectivity | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/check/"` |
| Validate credentials | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"host":"192.0.2.10","port":22,"username":"ops","password":"..."}' "${NODE_NEXUS_URL}/api/v1/nodes/validate-credentials"` |
| Validate (SSH key) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"host":"192.0.2.10","port":22,"username":"ops","ssh_key":"<key>","passphrase":"<pass>"}' "${NODE_NEXUS_URL}/api/v1/nodes/validate-credentials"` |
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

### Containers

| Task | Command |
|------|---------|
| List containers | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/"` |
| List all (incl. stopped) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers?all=true"` |
| Create container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","name":"my-ctr","command":"sleep 60"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers"` |
| Inspect container | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Start container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/start/"` |
| Stop container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stop/"` |
| Restart container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/restart/"` |
| Pause container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/pause/"` |
| Unpause container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/unpause/"` |
| Exec in container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec/"` |
| Container logs | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/logs?tail=100"` |
| Container stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stats"` |
| Container top | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/top"` |
| Delete container | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Prune containers | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/prune"` |

### Images

| Task | Command |
|------|---------|
| List images | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/"` |
| Pull image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","timeout":120}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/pull"` |
| Inspect image | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| Tag image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"repo":"local/alpine","tag":"v1.0"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/alpine:latest/tag"` |
| Delete image | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| Prune images | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/prune"` |

### Networks

| Task | Command |
|------|---------|
| List networks | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/networks"` |
| Create network | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-net","driver":"bridge"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/networks"` |
| Inspect network | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |
| Connect container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/connect"` |
| Disconnect container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/disconnect"` |
| Delete network | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |

### Volumes

| Task | Command |
|------|---------|
| List volumes | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/volumes"` |
| Create volume | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-vol","driver":"local"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/volumes"` |
| Inspect volume | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Delete volume | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Prune volumes | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/volumes/prune"` |

### System

| Task | Command |
|------|---------|
| Docker info | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/system/info"` |
| Disk usage | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/system/df"` |

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
| Export CSV | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/audit/export?fmt=csv"` |

## Dashboard & Search

| Task | Command |
|------|---------|
| Dashboard overview | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/dashboard/"` |
| Dashboard metrics | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/dashboard/metrics?group_by=day"` |
| Global search | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/search?q=deploy"` |

## Execution Stats

| Task | Command |
|------|---------|
| Command stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/commands/${CMD_ID}/stats"` |
| Script stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/scripts/${SCRIPT_ID}/stats"` |
| Node stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/stats"` |

## Node Tags

| Task | Command |
|------|---------|
| List node tags | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/tags"` |
| Add tags to node | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/tags"` |
| Remove tags from node | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/tags"` |

## SSE Event Stream

| Task | Command |
|------|---------|
| Subscribe to events | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/events/stream"` |

## Tag management

| Task | Command |
|------|---------|
| Rename tag | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"new_name":"new-tag"}' "${NODE_NEXUS_URL}/api/v1/tags/old-tag"` |
| Delete tag | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/tags/tag-to-delete"` |

## Clone

| Task | Command |
|------|---------|
| Clone command | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/commands/${CMD_ID}/clone?new_name=my-copy"` |
| Clone script | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/scripts/${SCRIPT_ID}/clone?new_name=my-copy"` |

## Favorites

| Task | Command |
|------|---------|
| List favorites | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/favorites"` |
| Add favorite | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"target_type":"command","target_id":"${CMD_ID}"}' "${NODE_NEXUS_URL}/api/v1/favorites"` |
| Remove favorite | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/favorites/command/${CMD_ID}"` |

## Notes

| Task | Command |
|------|---------|
| List notes | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/notes/command/${CMD_ID}"` |
| Create note | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"content":"TODO: review"}' "${NODE_NEXUS_URL}/api/v1/notes/command/${CMD_ID}"` |
| Update note | `curl -X PUT -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"content":"Updated"}' "${NODE_NEXUS_URL}/api/v1/notes/${NOTE_ID}"` |
| Delete note | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/notes/${NOTE_ID}"` |

## Health

| Task | Command |
|------|---------|
| Liveness | `curl "${NODE_NEXUS_URL}/health"` |
| Readiness | `curl "${NODE_NEXUS_URL}/ready"` |
| Metrics | `curl "${NODE_NEXUS_URL}/metrics"` |

See the [HTTP API reference](api.md) for the complete endpoint catalog and
[interactive docs](openapi.html) for request/response schemas.
