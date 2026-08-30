# Migration 1.x → 2.0

> Breaking — no compatibility. `1.7.2` → `2.0.0` `MAJOR` (`versioning.md`), prefix `/api/v1` → `/api/v2`.

## Prefix

```
v1: /api/v1/nodes, /api/v1/commands, /api/v1/docker/bulk/*
v2: /api/v2/nodes, /api/v2/commands, /api/v2/nodes/{id}/docker/*
v1 → 410 Gone (keep minimal 404 hint until 2.1)
```

## Pagination

```
v1: ?page=1&size=20 -> {items, total, page, size}
v2: ?cursor=<base64>&limit=20 -> {items, next_cursor, has_more, limit}
total removed (COUNT(*) expensive). Use has_more + next_cursor.
Example: GET /api/v2/nodes?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20
```

## Bulk (no bulk keyword)

```
v1: POST /nodes/bulk/delete {node_ids}, PATCH /nodes/bulk/update, POST /docker/bulk/exec {node_ids, container_id}
v2: POST /nodes/deletions {ids}, PATCH /nodes {updates:[{id, changes}]}, POST /nodes/{id}/docker/containers/executions {container_ids, command}
Single = ids=[id]. Fleet POST /docker/bulk/* removed — use POST /commands/executions for fleet.
Status: 200 all ok, 207 Multi-Status partial (succeeded>0 && failed>0), 422 all failed.
Envelope: {total, succeeded, failed, results:[{id,status:"success"|"error", error?, output?}]}
```

## Bulk create (new)

```
v1: POST /nodes {NodeCreate} (single)
v2: POST /nodes {items: [NodeCreate][1..20]} -> 201|207
Same for POST /commands {items}, POST /scripts {items}
```

## Docker (vert only, +9 ops)

```
Removed: POST /docker/bulk/* (fleet)
Added vert: POST /nodes/{id}/docker/containers/{cid}/kill {signal}, /update {memory,cpus}, GET|PUT /archive?path= (cp), GET /port, POST /wait, GET /system/version, POST /system/prune, POST /networks/prune, GET /images/{id}/history, POST /images/push
Vert bulk: POST /nodes/{id}/docker/containers/starts {container_ids}, /executions {container_ids, command} etc. (207)
```

## Compose (new, persistent)

```
compose_projects {id, node_id, project_name, compose, env, template_pack_id, UNIQUE(node_id, project_name)}
POST   /nodes/{id}/docker/compose/projects {project_name, compose, env?} -> 201 (pure DB)
GET    /nodes/{id}/docker/compose/projects ?cursor&limit
POST   /nodes/{id}/docker/compose/projects/{name}/ups {pull?,build?} -> 200|207 (separate deploy)
POST   /nodes/{id}/docker/compose/projects/{name}/downs etc. (no combined create+up)
```

## Templates (new)

```
POST   /templates/registries {owner,name,token?,branch} -> 201
POST   /templates/registries/{id}/syncs -> 200|207
POST   /templates/packs {manifest, commands, scripts, readme?, assets?} -> 201 local
GET    /templates/packs ?cursor&limit&registry_id&tag&installed?
POST   /templates/packs/{id}/installations -> 201|207|409 (409 on name conflict, no autorename, template_pack_id FK)
POST   /templates/packs/{id}/uninstallations -> 204
POST   /templates/packs/{id}/updates -> 200|207 (uninstall+install, WARN edits lost)
Repo hierarchy: templates/{pack_id}/{manifest.json, commands.json, scripts.json, README.md?, assets/{...}}
ScriptStep: {command_name?: string, command_id?: UUID} xor
```

## Notes → Description

```
Removed: GET|POST /notes/{type}/{id}, PUT /notes/{id}, DELETE /notes/{id}, DROP TABLE notes
Added: NodeModel.description Text nullable, PATCH /nodes/{id} {description}, GET /nodes/{id} {description}
commands|scripts description already existed.
```

## Stats (unified)

```
Removed: GET /dashboard, GET /dashboard/metrics, GET /.../metrics
Added: GET /{entity}/stats?group_by=day|hour|week|month (without group_by = snapshot ExecutionStatsResponse, with = {buckets: MetricsBucket[]})
GET /nodes/stats, GET /nodes/{id}/stats, GET /commands/stats, GET /commands/{id}/stats, GET /scripts/stats, GET /scripts/{id}/stats, GET /audit/stats
```

## Errors & Status

```
Unified ErrorResponse {code, message, request_id: string|null, detail: Json|null} (was request_id omitted)
New codes: 502 DockerError, 504 TimeoutError documented
clone: POST /commands/{id}/clone -> 201 (was 200)
pause/unpause: 204 (was 200 {status})
GET /scripts/{id}/schedule 200 null -> 404
CORS: allow_methods + OPTIONS,HEAD; remove X-API-Version (URL only)
```

## Tags / Filters

```
?tag -> ?tags everywhere, ?date_from&date_to unified (was from_date vs date_from)
tags split with filter empty, GIN ARRAY
```

## DB

```
alembic b1c2d3e4f5g6_2_0_bulk_first:
- add nodes.description
- add commands.template_pack_id, scripts.template_pack_id
- create template_registries, template_packs, template_assets, template_installations, compose_projects
- drop notes
Keep for migration until 2.1: credential_cipher legacy unprefixed, LEGACY_CONFIG_VERSION, _LEGACY_EXECUTION_STATUSES
```

## OpenAPI

```
version: 2.0.0, hash d8f7ccf9846a4958f4dd82282c83df6d4992d4bf94e110b2714783cad28d5825 -> new hash after v2
Use ENVIRONMENT=development for local (SECRET_KEY 32, ENCRYPTION_SALT 16)
```

