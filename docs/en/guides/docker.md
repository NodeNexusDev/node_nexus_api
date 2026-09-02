---
title: Manage remote Docker
status: stable
translation_key: guides.docker
source_revision: "2026-09-02"
---

# Manage remote Docker

Docker operations run through the node's SSH connection and require a reachable
Docker daemon on that host. Verify the node first, then list containers before
issuing state-changing operations. Bulk calls return `BulkResult` (`{total,succeeded,failed,results}`) with `200` all-ok or `207 Multi-Status` partial; a partial failure never rolls back successful remote operations.

## Containers

List running containers (cursor pagination):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
  # -> {items,next_cursor,has_more,limit}
```

List all containers including stopped:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?all=true&limit=20"
```

Create a container from an image. The `command` string is split into separate
arguments before being sent to Docker:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "image": "alpine:latest",
    "name": "my-ctr",
    "command": "sleep 60",
    "ports": {"80/tcp": "8080"},
    "volumes": {"/host": {"bind": "/container", "mode": "rw"}},
    "env": ["ENV_VAR=value"],
    "labels": {"com.example.foo": "bar"},
    "network": "bridge",
    "restart_policy": "always"
  }'
```

Inspect a container:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"
```

Use a returned container ID or name with `/start`, `/stop`, `/restart`,
`/pause`, `/unpause`, `/rename`, `/logs`, `/stats`, `/top`, `/exec`, plus new
single endpoints `/kill`, `/update`, `/archive`, `/port`, `/wait`.
State-changing calls require a read-write key:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"command": "id", "timeout": 30}'
```

Remove a container:

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"
```

View container logs:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/logs?tail=100"
```

Get container resource stats:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stats"
```

### New single-container operations (9 ops added in 2.0)

| Path | Method | Description |
|------|--------|-------------|
| `/containers/{id}/kill` | `POST` | Kill with signal `{"signal": "SIGTERM"}` → `{status:"killed"}` |
| `/containers/{id}/update` | `POST` | Update `{"memory": "512m", "cpus": "1.5", "restart_policy": "always"}` → `{status:"updated"}` |
| `/containers/{id}/archive?path=/etc/hosts` | `GET` | Copy file from container (`docker cp`) → `{output, path}` |
| `/containers/{id}/archive?path=/tmp/` | `PUT` | Copy data into container (`?path` query, `?data` body) → `{status:"copied"}` |
| `/containers/{id}/port` | `GET` | Port bindings `?private_port=80` → `{output, bindings}` |
| `/containers/{id}/wait` | `POST` | Wait for exit `?timeout=60` → `{exit_code}` |
| `/system/version` | `GET` | Docker version → `{server_version, api_version, go_version, git_commit, build_time, os, arch}` |
| `/system/prune` | `POST` | System prune `?volumes=true` → `{containers_deleted, images_deleted, space_reclaimed}` |
| `/networks/prune` | `POST` | Prune unused networks → `{output}` |
| `/images/{id}/history` | `GET` | Image history → `{layers:[{id,created,created_by,size,comment}]}` |
| `/images/push` | `POST` | Push image `{"image": "repo:tag"}` or `/images/{id}/push` → `{image,output,success}` |

Examples:

```bash
  # Kill
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"signal": "SIGKILL"}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/kill"

  # Update
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"memory": "512m", "cpus": "1.0"}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/update"

  # Archive get/put
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/etc/hosts"
curl --fail-with-body -X PUT -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/tmp/data&data=hello"

  # Port / Wait
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/port?private_port=80"
curl --fail-with-body -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/wait?timeout=60"
```

Prune stopped containers (still `POST /containers/prune`):

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"
```

## Images

Pull, inspect, tag, remove, and build images (lists are now cursor-paginated):

```bash
## List with cursor
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

## Pull
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/pull" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"image": "alpine:latest", "timeout": 120}'

## Inspect
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"

## History (new)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/history"

## Tag
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/tag" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"repo": "local/alpine", "tag": "v1.0"}'

## Push (new)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/push" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"image": "local/alpine:v1.0"}'
  # or POST /images/{id}/push

## Build from a Dockerfile passed through stdin
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/build" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "dockerfile": "FROM alpine:latest\nRUN echo hello > /marker",
    "tag": "local/built:v1",
    "build_args": {"VERSION": "1.0"},
    "no_cache": true
  }'

## Remove
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/local/alpine:v1.0"

## Prune unused images
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/prune"
```

## Networks

List, create, inspect, remove Docker networks and manage container membership (list now cursor-paginated). Prune is new:

```bash
## List networks
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

## Create a bridge network
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"name": "my-network", "driver": "bridge"}'

## Inspect a network
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"

## Connect a container to a network
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/connect" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_id": "${CONTAINER_ID}"}'

## Disconnect a container from a network
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/disconnect" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_id": "${CONTAINER_ID}"}'

## Remove a network
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"

## Prune unused networks (new)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/prune"
```

## Volumes

List, create, inspect, and remove Docker volumes (list now cursor-paginated):

```bash
## List volumes
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

## Create a named volume
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"name": "my-vol", "driver": "local"}'

## Inspect a volume
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"

## Remove a volume
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"

## Prune unused volumes
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/prune"
```

## System

Query Docker daemon information, version, and disk usage; prunes now cover system:

```bash
## Docker info
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/info"

## Version (new)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/version"

## Disk usage
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/df"

## System prune (new)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/prune?volumes=false"
```

## Vertical bulk operations (per-node, no fleet)

Fleet `POST /api/v2/docker/bulk/*` was removed. Use per-node vertical bulk under `POST /nodes/{id}/docker/...` (all return `BulkResult` with `207` partial). Single-container `ids=[id]` covers the single case. For fleet use `POST /commands/executions`.

Vert-bulk summary: `POST /nodes/{id}/docker/containers/{starts,stops,restarts,removals,pauses,unpauses,kills,updates,executions,inspections,logs,stats}` plus prunes (`/containers/prune`, `/images/prune`, `/volumes/prune`, `/networks/prune`, `/system/prune`) and per-container `kill`/`update`/`archive`/`port`/`wait`, networks/volumes/system (`info`/`df`/`version`/`prune`) and 9 new ops (see table above).

| Bulk path (POST) | Body | BulkResult item |
|------------------|------|-----------------|
| `/containers/starts` | `{"container_ids": ["<id>", ...]}` | `{container_id,status,error}` |
| `/containers/stops` | `{"container_ids": [...]}` query `?timeout=10` | same |
| `/containers/restarts` | `{"container_ids": [...]}` query `?timeout=10` | same |
| `/containers/removals` | `{"container_ids": [...]}` query `?force=false` | same |
| `/containers/pauses` | `{"container_ids": [...]}` | same |
| `/containers/unpauses` | `{"container_ids": [...]}` | same |
| `/containers/kills` | `{"container_ids": [...], "signal": "SIGTERM"}` | same |
| `/containers/updates` | `{"container_ids": [...], "memory": "512m", "cpus": "1.0", "restart_policy": "always"}` | same |
| `/containers/executions` | `{"container_ids": [...], "command": "id", "timeout": 30}` | `{container_id,status,error,stdout,stderr,exit_code}` |
| `/containers/inspections` | `{"container_ids": [...]}` | `{container_id,status,error,data: DockerContainerInspect}` |
| `/containers/logs` | `{"container_ids": [...], "tail": 100, "since": null}` | `{container_id,status,error,logs}` |
| `/containers/stats` | `{"container_ids": [...]}` | `{container_id,status,error,stats: DockerStats}` |
| `/images/pulls` | `{"images": ["alpine:latest"], "timeout": 300}` | `{image,status,error,output}` |
| `/images/removals` | `{"image_ids": [...]}` | `{image,status,error}` |
| `/networks/removals` | `{"network_ids": [...]}` | `{network_id,status,error}` |
| `/volumes/removals` | `{"volume_names": [...]}` | `{volume_name,status,error}` |
| `/containers/prune` | — (system service) | `DockerPruneResponse` (not BulkResult) |
| `/images/prune` | — | `DockerPruneResponse` |
| `/volumes/prune` | — | `DockerVolumePruneResponse` |
| `/networks/prune` | — | `DockerVolumePruneResponse` |
| `/system/prune` | `?volumes=false` | `DockerPruneResponse` |

Examples (`207` on partial):

```bash
  # Vert-bulk restart
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/restarts?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_ids": ["app-ctr", "sidecar"]}'
  # {"total":2,"succeeded":1,"failed":1,"results":[{"container_id":"app-ctr","status":"success"}, ...]}

  # Vert-bulk exec
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_ids": ["app-ctr"], "command": "id", "timeout": 30}'

  # Vert-bulk stats
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/stats" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_ids": ["app-ctr"]}'
```

Inspect every item in `results` after a bulk call; `200` means all succeeded, `207` means `succeeded>0 && failed>0`.

## Validation and security

Identifiers, image names, and timeouts are validated before a remote command is
built. Still use a least-privilege SSH account and treat container execution as
privileged remote access. Inspect every item in `results` after a bulk call.
