---
title: Template packs and registries
description: Share reusable command and script bundles via registries and packs with assets and installations.
status: stable
translation_key: guides.templates
source_revision: "2026-09-02"
---

# Template packs and registries

Templates provide reusable bundles of commands, scripts, and asset files.
They are isolated from nodes, commands, scripts, Docker, and compose, and are
managed under `/api/v2/templates`. Two layers exist: registries (GitHub sources)
and packs (the actual bundles).

A pack on disk follows the repository convention:

```
templates/{pack_id}/
  manifest.json
  commands.json
  scripts.json
  README.md           # optional
  assets/
    docker-compose.yml
    nginx.conf
    ...
```

`pack_id` is the filesystem directory name (unique inside a registry). The API
stores metadata in `template_packs` (`{id, registry_id, pack_id, name, description, version, author, tags, manifest_sha, readme, installed_version, installed_at}`), assets in `template_assets` (`{id, pack_id, path, size, sha, content}`) with unique `(pack_id, path)`, installation links in `template_installations` (`{id, pack_id, entity_type, entity_id}`), and registry records in `template_registries` (`{id, owner, name, default_branch, last_synced_at}`).

`tags` are `ARRAY(String)` (GIN indexed, JSON fallback for SQLite) and `manifest_sha` is the hash of the manifest for change detection. `ScriptStep` inside `scripts.json` uses `{command_name?: string, command_id?: UUID}` xor — one of the two resolves the step.

All list endpoints use cursor pagination (`?cursor=<base64>&limit=20 → {items,next_cursor,has_more,limit}`) with `422` on an invalid cursor. Bulk results use the unified envelope `BulkResult` (`{total,succeeded,failed,results}`) with `200` or `207 Multi-Status`. Mutations require a read-write key.

## Registries (GitHub sources)

Registries point to a GitHub repository that hosts `templates/{pack_id}/` trees on a default branch.

### Create a registry

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/templates/registries" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "owner": "my-org",
    "name": "node-nexus-templates",
    "github_token": "ghp_xxx",
    "default_branch": "main"
  }'
  # -> 201 {id, owner, name, default_branch, last_synced_at, created_at, updated_at}
```

`github_token` is optional (needed for private repos) and never returned. `409` on duplicate `(owner, name)`.

### List / get / delete registries

```bash
  # List (cursor)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
  # -> {items, next_cursor, has_more, limit}

  # Get one
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}"

  # Delete
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}"
  # -> 204 No Content
```

### Sync a registry

Fetches `templates/{pack_id}/` from GitHub, upserts packs, and returns per-pack results with `200` or `207`.

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}/syncs"
  # -> {registry_id, total, succeeded, failed, results:[{pack_id,status:"success"|"error",error,message}]}
```

`total` counts discovered pack directories; `succeeded`/`failed` summarize file parsing and DB upserts. `404` when the registry does not exist; partial syncs return `207`.

## Packs

Packs can be synced from a registry or created locally via the API.

### Create a local pack

Inline assets are base64-encoded. `manifest.manifest_sha` is optional and stored as `manifest_sha`.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/templates/packs" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "manifest": {
      "pack_id": "docker-install",
      "name": "Docker Install",
      "description": "Install Docker and compose",
      "version": "1.0.0",
      "author": "Ops Team",
      "tags": ["docker","setup"],
      "manifest_sha": "abc123"
    },
    "commands": [
      {
        "name": "install-docker",
        "command": "curl -fsSL https://get.docker.com | sh",
        "parameters": [],
        "tags": ["docker"],
        "description": "Install Docker"
      }
    ],
    "scripts": [
      {
        "name": "setup-stack",
        "description": "Full setup",
        "steps": [
          {"label": "install", "type": "command", "command": "curl -fsSL https://get.docker.com | sh", "on_failure": "stop"}
        ],
        "tags": ["docker"]
      }
    ],
    "readme": "# Docker Install\n...",
    "assets": [
      {"path": "assets/docker-compose.yml", "content_base64": "dmVyc2lvbjogJzMuOCcK..."},
      {"path": "assets/nginx.conf", "content_base64": "c2VydmVyIHsK..."}
    ],
    "registry_id": null
  }'
  # -> 201 {id, registry_id, pack_id, name, description, version, author, tags, manifest_sha, readme, installed_version, installed_at, created_at, updated_at, assets:[{id, pack_id, path,size,sha,created_at,updated_at}]}
```

Provide `registry_id` only when the pack logically belongs to a registry created in the same environment. `409` when `pack_id` already exists in that registry scope.

### List packs with filters

Cursor pagination plus optional filters: `registry_id`, `tag`, `installed`, `search` (name/description ILIKE).

```bash
  # All packs
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

  # By registry
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?registry_id=${REGISTRY_ID}&limit=20"

  # By tag
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?tag=docker&limit=20"

  # By installed flag
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?installed=true&limit=20"

  # Search
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs?search=docker&limit=20"
```

Response is `CursorPage[PackResponse]` (`{items, next_cursor, has_more, limit}`); each `PackResponse` carries `{id, registry_id, pack_id, name, description, version, author, tags, manifest_sha, readme, installed_version, installed_at, created_at, updated_at}`.

### Get pack detail and archive

```bash
  # Detail with assets
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}"
  # -> {id, ..., assets:[{id, pack_id, path, size, sha, created_at, updated_at}]}

  # Stream assets as tar
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --output pack.tar \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/archive"
  # -> application/x-tar, Content-Disposition: attachment; filename="<pack_id>.tar"
  # Empty tar when the pack has no assets. Alias: /packs/{id}/assets/archive

  # Installation links (cursor pagination)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
  # -> {items:[{id, pack_id, entity_type:"command"|"script", entity_id, created_at}], next_cursor, has_more, limit}

  # Stats
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/stats"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/stats?group_by=tag"
  # -> {total, installed, not_installed, buckets:[{group,total,installed,not_installed}]}
```

`404` when the pack does not exist.

## Install, uninstall, update

Installation materializes pack contents as real commands and scripts with `template_pack_id` FK, linked through `template_installations`. `on_conflict` controls name collisions.

```bash
  # Install — creates commands/scripts with template_pack_id FK (201|207|409)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?on_conflict=fail"
  # -> {total,succeeded,failed,results:[{entity_type,entity_id,name,status:"success"|"error",error}]}
  # on_conflict=fail (default) → 409 on existing command/script name
  # on_conflict=rename      → appends _1, _2 etc.

  # Install with rename strategy
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?on_conflict=rename"

  # Uninstall — removes entities created by the last installation
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/uninstallations"
  # -> 204 No Content

  # Update — uninstall+install atomically, warn: local edits to generated commands/scripts are lost
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/updates?on_conflict=fail"
  # -> 200|207 {total,succeeded,failed,results:[...]}  (409 on fail conflict)
```

`201` when all installations succeed, `207` when partially succeeded. Inspect `results[]` for per-entity `status`/`error`. Uninstall/install are not transactional across remote nodes — treat `207` as partial materialization.

## Hierarchy and conventions

- Repository root contains `templates/{pack_id}/manifest.json` at minimum plus `commands.json` / `scripts.json` depending on content.
- Assets live under `templates/{pack_id}/assets/` and are uploaded via base64 `content_base64`; server persists decoded bytes, `size`, and `sha`.
- `GET /packs/{id}/archive` streams the stored assets as `application/x-tar`; use it to download a pack's asset bundle.
- `GET /packs/{id}/installations` lists `template_installations` links pointing to the created `commands`/`scripts` rows.
- `tags` enable discovery (`?tag=`) and are indexed via GIN; `manifest_sha` lets clients detect updates without re-downloading assets.
- Compose projects can reference a pack via `template_pack_id` — see [Docker Compose](compose.md).

## Validation and security

`owner`, `name`, and `pack_id` lengths are enforced (255/100). `github_token` is optional and redacted. Binary assets must be base64-encoded; oversized or malformed payloads yield `422`. Sync failures for individual packs do not roll back other successful pack upserts in the same sync (`207`). Require a read-write key for `POST /registries`, `DELETE`, `syncs`, `packs`, `installations`, `uninstallations`, and `updates`.
