---
title: Cheat sheet
status: stable
translation_key: reference.cheat-sheet
source_revision: "2026-09-02"
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
| List nodes | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/?cursor=&limit=20"` |
| List with tags | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/?tags=production&tags=frontend"` |
| Bulk create nodes | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"items": [{"name":"srv","host":"192.0.2.10","port":22,"connection_type":"ssh","username":"ops","password":"...","tags":["prod"]}]}' "${NODE_NEXUS_URL}/api/v2/nodes/"` |
| Get one node | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Update single node | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["prod","db"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Bulk update nodes | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"updates": [{"id":"${NODE_ID}","changes":{"tags":["prod","db"]}}]}' "${NODE_NEXUS_URL}/api/v2/nodes/"` |
| Delete node | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Bulk delete | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/deletions"` |
| Bulk check | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/checks"` |
| Bulk metrics | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/metrics"` |
| Bulk credential validations | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>"],"tags":["prod"]}' "${NODE_NEXUS_URL}/api/v2/nodes/credential-validations"` |
| Status history | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/status-history?cursor=&limit=20"` |

Bulk responses use `BulkResult` `{total,succeeded,failed,results}` with `200` all ok, `207` partial, `422` all failed.

## Commands

| Task | Command |
|------|---------|
| Bulk create commands | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"items": [{"name":"disk","command":"df -h {{ mount }}","parameters":[{"name":"mount","type":"string","required":true}]}]}' "${NODE_NEXUS_URL}/api/v2/commands/"` |
| List templates | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/?cursor=&limit=20"` |
| Get command | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}"` |
| Update command | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"description":"updated"}' "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}"` |
| Delete command | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}"` |
| Execute commands on nodes (M×N) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command_ids":["<cmd1>"],"node_ids":["<id1>","<id2>"],"node_tags":[],"params":{"<cmd1>":{"mount":"/"}}}' "${NODE_NEXUS_URL}/api/v2/commands/executions"` |
| Execute raw commands (M×N) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"commands":["uptime","df -h"],"node_ids":["<id1>"]}' "${NODE_NEXUS_URL}/api/v2/commands/raw-executions"` |
| Command history | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/history?node_id=${NODE_ID}&cursor=&limit=20"` |
| Executions history | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/executions/history?batch_id=${BATCH_ID}&cursor=&limit=20"` |
| Bulk retry | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"execution_ids":["<exec1>"]}' "${NODE_NEXUS_URL}/api/v2/commands/executions/retries"` |
| Bulk cancel | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"execution_ids":["<exec1>"]}' "${NODE_NEXUS_URL}/api/v2/commands/executions/cancels"` |

## Docker

### Containers

| Task | Command |
|------|---------|
| List containers | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/?cursor=&limit=20"` |
| List all (incl. stopped) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?all=true&cursor=&limit=20"` |
| Create container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","name":"my-ctr","command":"sleep 60"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers"` |
| Inspect container | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Start container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/start"` |
| Stop container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stop?timeout=10"` |
| Restart container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/restart?timeout=10"` |
| Pause container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/pause"` |
| Unpause container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/unpause"` |
| Kill container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"signal":"SIGKILL"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/kill"` |
| Update container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"memory":"512m","cpus":"1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/update"` |
| Exec in container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec"` |
| Container logs | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/logs?tail=100"` |
| Container stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stats"` |
| Container top | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/top"` |
| Get archive (cp from) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/etc/hosts"` |
| Put archive (cp to) | `curl -X PUT -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/tmp/data"` |
| Port | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/port?private_port=80"` |
| Wait | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/wait?timeout=30"` |
| Delete container | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Prune containers | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"` |
| Bulk start | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>","<cid2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/starts"` |
| Bulk stop | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/stops?timeout=10"` |
| Bulk restart | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/restarts?timeout=10"` |
| Bulk remove | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/removals?force=false"` |
| Bulk pause | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/pauses"` |
| Bulk unpause | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/unpauses"` |
| Bulk kill | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"],"signal":"SIGKILL"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/kills"` |
| Bulk update | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"],"memory":"512m","cpus":"1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/updates"` |
| Bulk executions | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>","<cid2>"],"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/executions"` |
| Bulk inspections | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/inspections"` |
| Bulk logs | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"],"tail":100}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/logs"` |
| Bulk stats | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/stats"` |

### Images

| Task | Command |
|------|---------|
| List images | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/?cursor=&limit=20"` |
| Pull image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","timeout":120}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/pull"` |
| Build image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"dockerfile":"FROM alpine","tag":"my:1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/build"` |
| Bulk pulls | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"images":["alpine:latest"],"timeout":120}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/pulls"` |
| Bulk removals | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image_ids":["alpine:latest"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/removals"` |
| Inspect image | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| Image history | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/history"` |
| Tag image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"repo":"local/alpine","tag":"v1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/tag"` |
| Push image (path) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/push"` |
| Push image (body) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/push"` |
| Delete image | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| Prune images | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/prune"` |

### Networks

| Task | Command |
|------|---------|
| List networks | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks?cursor=&limit=20"` |
| Create network | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-net","driver":"bridge"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks"` |
| Inspect network | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |
| Bulk removals | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"network_ids":["<net1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/removals"` |
| Prune networks | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/prune"` |
| Connect container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/connect"` |
| Disconnect container | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/disconnect"` |
| Delete network | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |

### Volumes

| Task | Command |
|------|---------|
| List volumes | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes?cursor=&limit=20"` |
| Create volume | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-vol","driver":"local"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes"` |
| Inspect volume | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Bulk removals | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"volume_names":["<vol1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/removals"` |
| Delete volume | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Prune volumes | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/prune"` |

### System

| Task | Command |
|------|---------|
| Docker info | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/info"` |
| Docker version | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/version"` |
| Disk usage | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/df"` |
| System prune | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/prune?volumes=false"` |
| Prune containers | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"` |
| Prune images | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/prune"` |

## Compose

| Task | Command |
|------|---------|
| Create compose project | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"project_name":"myapp","compose":"services:\n  web:\n    image: nginx"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects"` |
| List compose projects | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects?cursor=&limit=20"` |
| Get compose project | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}"` |
| Update compose project | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"compose":"services:\n  web:\n    image: nginx:1.25"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}"` |
| Delete compose project | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}"` |
| Compose up | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"pull":true}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/ups"` |
| Compose down | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"volumes":false}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/downs"` |
| Compose ps | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/ps"` |
| Compose logs | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/logs?tail=100"` |
| Compose config | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/config"` |
| Compose exec | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"service":"web","command":"ls"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/executions"` |

## Templates

| Task | Command |
|------|---------|
| Create registry | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"owner":"myorg","name":"templates","default_branch":"main"}' "${NODE_NEXUS_URL}/api/v2/templates/registries"` |
| List registries | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/registries?cursor=&limit=20"` |
| Sync registry | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}/syncs"` |
| Create pack (local) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"manifest":{"pack_id":"my-pack","name":"My Pack","version":"1.0.0"},"commands":[],"scripts":[]}' "${NODE_NEXUS_URL}/api/v2/templates/packs"` |
| List packs | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs?cursor=&limit=20"` |
| Get pack | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}"` |
| Pack archive | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/archive" --output pack.tar` |
| Install pack | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?on_conflict=fail"` |
| Uninstall pack | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/uninstallations"` |
| Update pack | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/updates?on_conflict=fail"` |
| List installations | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?cursor=&limit=20"` |

## Scripts

| Task | Command |
|------|---------|
| Bulk create scripts | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"items": [{"name":"deploy","steps":[{"command":"uptime"}]}]}' "${NODE_NEXUS_URL}/api/v2/scripts/"` |
| List scripts | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/?cursor=&limit=20"` |
| Retry script | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/executions/${EXECUTION_ID}/retry"` |
| Cancel execution | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/executions/${EXECUTION_ID}/cancel"` |
| Schedule history | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/schedule/history?cursor=&limit=20"` |

## Configuration

| Task | Command |
|------|---------|
| Export | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/config/export"` |
| Import | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v2/config/import"` |
| Dry-run import | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"dry_run":true,"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v2/config/import"` |

## API keys

| Task | Command |
|------|---------|
| Create key | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"reader","scope":"read-only"}' "${NODE_NEXUS_URL}/api/v2/api-keys/"` |
| List keys | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/api-keys/?cursor=&limit=20"` |
| Update key | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"is_active":false}' "${NODE_NEXUS_URL}/api/v2/api-keys/${KEY_ID}"` |
| Delete key | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/api-keys/${KEY_ID}"` |

## Audit

| Task | Command |
|------|---------|
| Query events | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?cursor=&limit=20"` |
| Filter by node | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?node_id=${NODE_ID}"` |
| Audit stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats"` |
| Delete log | `curl -X DELETE -H "X-API-Key: ${MASTER_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?confirm=yes"` |
| Export CSV | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/export?fmt=csv"` |

## Search

| Task | Command |
|------|---------|
| Global search | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/search?q=deploy"` |

## Execution Stats

| Task | Command |
|------|---------|
| Command stats (snapshot) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/stats"` |
| Command stats (buckets) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/stats?group_by=day"` |
| Command per-id stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${CMD_ID}/stats"` |
| Script stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/stats"` |
| Node stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/stats"` |
| Nodes stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/stats?group_by=day"` |
| Audit stats | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=day"` |

## Node Tags

| Task | Command |
|------|---------|
| List node tags | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/tags"` |
| Add tags to node | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/tags"` |
| Remove tags from node | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/tags"` |

## SSE Event Stream

| Task | Command |
|------|---------|
| Subscribe to events | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/events/stream"` |

## Tag management

| Task | Command |
|------|---------|
| Rename tag | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"new_name":"new-tag"}' "${NODE_NEXUS_URL}/api/v2/tags/old-tag"` |
| Delete tag | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/tags/tag-to-delete"` |

## Clone

| Task | Command |
|------|---------|
| Clone command | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${CMD_ID}/clone?new_name=my-copy"` |
| Clone script | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/clone?new_name=my-copy"` |

## Favorites

| Task | Command |
|------|---------|
| List favorites | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/favorites"` |
| Add favorite | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"target_type":"command","target_id":"${CMD_ID}"}' "${NODE_NEXUS_URL}/api/v2/favorites"` |
| Remove favorite | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/favorites/command/${CMD_ID}"` |

## Health

| Task | Command |
|------|---------|
| Liveness | `curl "${NODE_NEXUS_URL}/health"` |
| Readiness | `curl "${NODE_NEXUS_URL}/ready"` |
| Metrics | `curl "${NODE_NEXUS_URL}/metrics"` |

See the [HTTP API reference](api.md) for the complete endpoint catalog and
[interactive docs](openapi.html) for request/response schemas.
