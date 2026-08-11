---
title: Manage remote Docker
status: stable
translation_key: guides.docker
source_revision: "2026-08-11"
---

# Manage remote Docker

Docker operations run through the node's SSH connection and require a reachable
Docker daemon on that host. Verify the node first, then list containers before
issuing state-changing operations. Bulk calls return individual results; a
partial failure does not roll back successful remote operations.

## Containers

List running containers:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers"
```

Create a container from an image. The `command` string is split into separate
arguments before being sent to Docker:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers" \
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

Use a returned container ID or name with `/start`, `/stop`, `/restart`, `/logs`,
`/stats`, or `/exec`. State-changing calls require a read-write key:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"command": "id", "timeout": 30}'
```

## Images

Pull, inspect, tag, remove, and build images:

```bash
## Pull
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/pull" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"image": "alpine:latest", "timeout": 120}'

## Inspect
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/alpine:latest"

## Tag
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/alpine:latest/tag" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"repo": "local/alpine", "tag": "v1.0"}'

## Build from a Dockerfile passed through stdin
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/build" \
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
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/local/alpine:v1.0"
```

## Bulk operations

Bulk endpoints under `/api/v1/docker/bulk/` act on multiple nodes. You can
provide explicit `node_ids`, `node_tags`, or both. Tags are resolved to Docker
nodes and merged with explicit IDs. Results are returned per node; a partial
failure does not roll back successful remote operations.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v1/docker/bulk/restart" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "node_ids": [],
    "node_tags": ["prod"],
    "container_id": "app-ctr",
    "timeout": 30
  }'
```

At least one of `node_ids` or `node_tags` is required. `bulk/exec` also requires
a `command` field.

## Validation and security

Identifiers, image names, and timeouts are validated before a remote command is
built. Still use a least-privilege SSH account and treat container execution as
privileged remote access. Inspect every item in `results` after a bulk call.
