---
title: Docker Compose projects
description: Persist compose projects per node and manage lifecycle via compose verbs.
status: stable
translation_key: guides.compose
source_revision: "2026-09-02"
---

# Docker Compose projects

Compose support is isolated from plain Docker container management. A compose
project is a persisted record in `compose_projects` (`{id, node_id, project_name, compose, env, template_pack_id, UNIQUE(node_id, project_name)}`) and is created as pure database state. Deployment is a separate step — creating a project does not run `compose up`. All compose operations are scoped per node under `/api/v2/nodes/{id}/docker/compose` and require a reachable Docker daemon with `docker compose` on that host. Mutations need a read-write key (or JWT with write scope).

`env` is stored as JSON (`{ "VAR": "value" }`) and maps to the compose `.env` on the remote host. `template_pack_id` is an optional foreign key to a template pack that produced the project. `project_name` is validated as `^[a-zA-Z0-9][a-zA-Z0-9_.-]*$` and limited to 100 characters; it is unique per node.

Bulk verbs that act on multiple services return `BulkResult` (`{total,succeeded,failed,results:[{service,status:"success"|"error",error,output}]}`) with `200` when all succeed or `207 Multi-Status` when partially succeeded. Project list endpoints use cursor pagination (`?cursor=<base64>&limit=20 → {items,next_cursor,has_more,limit}`); an invalid cursor yields `422`.

## Create a project (pure DB)

No remote call is made; the record is only stored in PostgreSQL.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name": "web-stack",
    "compose": "services:\n  web:\n    image: nginx:alpine\n    ports:\n      - \"8080:80\"\n",
    "env": {"NGINX_HOST": "example.com"},
    "template_pack_id": null
  }'
  # -> 201 {id, node_id, project_name, compose, env, template_pack_id, created_at, updated_at}
```

`env` can be omitted or empty; it replaces the entire map on update. `409` is returned when `(node_id, project_name)` already exists.

## List projects (cursor pagination)

```bash
  # First page
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects?limit=20"

  # Next page
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # -> {items, next_cursor, has_more, limit}
```

The cursor encodes `{"offset": N}` as base64url JSON. Iterate while `has_more` is true; `next_cursor` is `null` on the last page.

## Get, update, delete a project (pure DB)

```bash
  # Get by name
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack"

  # Patch (partial) — only sent fields are updated, env replaces all keys
curl --fail-with-body -X PATCH \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "compose": "services:\n  web:\n    image: nginx:1.25\n",
    "env": {"NGINX_HOST": "new.example.com"}
  }'

  # Unlink from template pack
curl --fail-with-body -X PATCH \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"template_pack_id": null}'

  # Delete (pure DB, no remote teardown)
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack"
  # -> 204 No Content
```

Deleting the DB record does not run `compose down`. Tear down with `/downs` first if needed. `404` when the project is not found.

## Deploy and lifecycle operations

Deploy is explicit. `404` when `project_name` does not exist. `207` for service-level partial failures.

### `up` / `down`

```bash
  # Up — equivalent to `docker compose up -d [--build] [--pull]` (per service BulkResult, 200|207)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/ups" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"pull": false, "build": true, "services": ["web"]}'
  # -> {total,succeeded,failed,results:[{service,status,error,output}]}

  # Up with pull + build + all services
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/ups" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"pull": true, "build": true}'

  # Down — `docker compose down` (-v volumes, --remove-orphans, -t timeout, --rmi images=all|local)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/downs" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"volumes": false, "remove_orphans": true, "timeout": 30, "images": null}'
  # -> {status:"down", output:"..."}
```

Omit `services` to target all services.

### Verb bulk (`207`)

All verbs below are `POST /nodes/{id}/docker/compose/projects/{name}/{verb}` returning `BulkResult` with `200` or `207`. Body is `{services?: ["name"]}` except `kills` (`{signal?, services?}`).

| Path suffix | Compose command | Extra query | Body | BulkResult item |
|-------------|-----------------|-------------|------|-----------------|
| `/starts` | `compose start` | — | `{services?:[]}` | `{service,status,error,output}` |
| `/stops` | `compose stop` | `?timeout=10` (1..600) | `{services?:[]}` | same |
| `/restarts` | `compose restart` | `?timeout=10` | `{services?:[]}` | same |
| `/pauses` | `compose pause` | — | `{services?:[]}` | same |
| `/unpauses` | `compose unpause` | — | `{services?:[]}` | same |
| `/kills` | `compose kill` | — | `{"signal":"SIGTERM", services?:[]}` | same |
| `/creates` | `compose create` | — | `{services?:[]}` | same |
| `/rms` | `compose rm -f [-v]` | `?volumes=false` | `{services?:[]}` | same |
| `/pulls` | `compose pull` | — | `{services?:[]}` | same |
| `/pushs` | `compose push` | — | `{services?:[]}` | same |
| `/builds` | `compose build [--no-cache]` | `?no_cache=false` | `{services?:[]}` | same |

Examples:

```bash
  # Start / Stop / Restart
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web","api"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/starts"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/stops?timeout=30"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/restarts?timeout=30"

  # Pause / Unpause
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/pauses"
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/unpauses"

  # Kill with signal / Rm with volumes / Build --no-cache / Pull / Push
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"signal": "SIGKILL", "services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/kills"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/rms?volumes=true"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/builds?no_cache=true"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/pulls"

curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/pushs"

  # Create services (no start)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"services": ["web"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/creates"
```

Inspect each element in `results`; `200` means all succeeded, `207` means `succeeded>0 && failed>0`.

### Exec and run

```bash
  # Exec in running service — `compose exec <service> <command>` (-> {stdout,stderr,exit_code})
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"service": "web", "command": "nginx -t", "timeout": 30}'

  # Run one-off — `compose run [--detach] <service> [command]` (-> {output})
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/runs" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"service": "web", "command": "echo hello", "detached": false, "timeout": 60}'
```

`service` is required; `command` for `run` is optional (uses image `CMD`). Timeouts are 1..600 seconds.

### Inspect operations (GET)

| Path | Query | Response |
|------|-------|----------|
| `GET .../ps` | `?all=false` | `{output, containers:[{...}]}` (`compose ps`) |
| `GET .../logs` | `?tail=100&since=...&services=web` | `{output, logs}` (`compose logs --tail`) |
| `GET .../config` | — | `{config, output}` (`compose config` resolved YAML) |
| `GET .../images` | — | `{images:[...], output}` (`compose images`) |
| `GET .../top` | `?service=web` | `{titles:[...], processes:[[...]], output}` |
| `GET .../port` | `?service=web&private_port=80` (both required) | `{output, bindings}` |
| `GET .../version` | — | `{version, output}` (`compose version`) |

Examples:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/ps?all=true"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/logs?tail=200&services=web"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/config"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/images"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/top?service=web"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/port?service=web&private_port=80"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/web-stack/version"
```

## Error handling

- `422` for invalid `project_name`, invalid `compose` YAML (empty/oversized >1MiB), invalid `services` names, invalid query values (`timeout` out of range, bad cursor), or oversized `env` JSON.
- `404` when the referenced compose project does not exist on that node.
- `207` envelope must be inspected per `results[]`; successful service operations are not rolled back on partial failure.
- `401/403` for missing or read-only credentials on state-changing calls.

## Validation and security

`project_name` is strictly validated; `compose` content is size-limited and passed verbatim to the remote `compose` binary over SSH. `env` values are JSON strings. Obtain the node first, list projects, then deploy. Treat compose verbs as privileged — they execute arbitrary images/commands on the node.
