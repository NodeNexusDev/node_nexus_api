---
title: Manage nodes
status: stable
translation_key: guides.nodes
source_revision: "2026-09-02"
---

# Manage nodes

Nodes represent remote servers reachable over SSH. Each node stores an encrypted
credential, connectivity metadata, tags, a `description` field, and a last-checked status.

> **Notes removed in 2.0:** the `notes` table and `/api/v2/notes/*` endpoints are
> gone — description field replaces notes. Use `description` on the node itself (`PATCH /api/v2/nodes/{id} {"description": "..."}`) — `GET /api/v2/nodes/{id}` now returns `description`. Existing `commands`/`scripts` already had `description`.

## Create nodes (bulk)

Bulk-first without the `bulk` keyword. `POST /api/v2/nodes/` now accepts an envelope
`{items: [NodeCreate, ...]}` (1..20 items) and returns a `BulkResult` with HTTP `201` when all succeed or `207 Multi-Status` on partial success (201|207 BulkResult). Pure failure also returns `200` per the bulk envelope contract. Example: `POST /api/v2/nodes/` with `{items:[{name,host,port,connection_type,tags,description,has_docker,docker_host}]}` → 201|207.

Request fields per item: `name`, `host`, `port` (1..65535, default 22), `connection_type` (`ssh`), `username`, `password` / `ssh_key` + optional `passphrase`, `tags` (array), `description` (max 1000, nullable), `has_docker` (bool), `docker_host` (requires `has_docker=true`, validated).

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "name": "web-01",
        "host": "192.0.2.10",
        "port": 22,
        "connection_type": "ssh",
        "username": "ops",
        "password": "change-me",
        "tags": ["production", "frontend"],
        "description": "Primary frontend",
        "has_docker": true,
        "docker_host": "unix:///var/run/docker.sock"
      }
    ]
  }'
```

Response `201` (all ok) or `207` (partial):

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "results": [
    {"node_id": "550e8400-e29b-41d4-a716-446655440000", "status": "success", "error": ""}
  ]
}
```

On partial failure the envelope still contains per-item `status: "success" | "error"` and `error` text; successful creates are persisted, failed ones are not rolled back. `BulkResult` shape: `{total, succeeded, failed, results:[{id,status,error,output?}]}`.

Save returned `node_id` values for metrics, command execution, and checks.

### SSH key authentication

Instead of a password, pass the private key content in `ssh_key`. If the key
is encrypted, supply the passphrase:

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [{
      "name": "web-02",
      "host": "192.0.2.11",
      "port": 22,
      "connection_type": "ssh",
      "username": "ops",
      "ssh_key": "<private-key-content>",
      "passphrase": "key-passphrase",
      "tags": [],
      "description": "SSH key auth node"
    }]
  }'
```

`passphrase` is optional and only required when the SSH private key is
encrypted. Both `password`, `ssh_key`, and `passphrase` are encrypted at
rest and never returned in API responses (`GET /nodes/{id}` returns `description`, `has_docker`, `docker_host` but no secrets).

## Validate credentials

Check SSH connectivity with provided credentials without saving a node to the
database. Useful for verifying reachability before creating a node.

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/validate-credentials" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "host": "192.0.2.10",
    "port": 22,
    "username": "ops",
    "password": "change-me"
  }'
```

SSH key validation also works — replace `password` with `ssh_key`
(and optionally `passphrase`):

Response on success:

```json
{
  "status": "active",
  "message": "SSH connection successful"
}
```

Response on failure:

```json
{
  "status": "unreachable",
  "message": "Connection refused"
}
```

## List and filter (cursor pagination)

Cursor pagination only. `total`/`page`/`size` were removed (`COUNT(*)` expensive).
Use `limit` + opaque `cursor` → `{items, next_cursor, has_more, limit}`.

```bash
  # First page
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?limit=20"

  # Next page — cursor from previous response
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # cursor=eyJvZmZzZXQiOjIwfQ== decodes to {"offset":20} (base64url JSON)
```

Response shape:

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "web-01",
      "host": "192.0.2.10",
      "port": 22,
      "connection_type": "ssh",
      "status": "active",
      "username": "ops",
      "docker_host": null,
      "has_docker": false,
      "tags": ["production"],
      "description": "Primary frontend",
      "created_at": "2026-09-02T10:00:00Z",
      "updated_at": "2026-09-02T10:00:00Z"
    }
  ],
  "next_cursor": "eyJ0cyI6IjIwMjYtMDktMDJUMTA6MDA6MDBaIiwiaWQiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAifQ==",
  "has_more": true,
  "limit": 20
}
```

Iterate while `has_more` is true, passing `next_cursor` as `cursor`. `next_cursor` is `null` on the last page. Invalid cursors return `422`.

Filter by tags with AND matching:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tags=production' \
  --data-urlencode 'tags=frontend' \
  "${NODE_NEXUS_URL}/api/v2/nodes/?limit=20"
```

Search by name/host:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?search=web&limit=20"
```

Offset `page`/`size` is no longer accepted for this endpoint — use `cursor`/`limit`.

## Single-node CRUD

```bash
  # Get
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"

  # Update (partial) — description replaces notes
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"description": "Updated inline docs", "tags": ["production"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"

  # Delete
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"
  # 204 No Content
```

## Verify connectivity (single)

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/check/"
```

A successful check confirms SSH reachability. The node status is updated
automatically.

## System metrics (single)

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/metrics/"
```

Returns CPU, memory, disk, and load information from the remote host.

## Command history (per node)

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/commands/history?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

Returns a cursor-paginated list of commands executed on this node (`{items,next_cursor,has_more,limit}`). Each record contains
the command fingerprint, exit code, truncated stdout/stderr with original byte
counts, and execution time. Output is bounded by the `bound_output()` policy to
prevent unbounded growth.

## Status history (cursor)

Query the history of status changes (active/unreachable/error) for a node with cursor pagination (`CursorPage`, offset-encoded cursor):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/status-history?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

Response:

```json
{
  "items": [
    {"id": "...", "node_id": "...", "old_status": "unreachable", "new_status": "active", "source": "check", "changed_at": "2026-09-02T10:00:00Z"}
  ],
  "next_cursor": "eyJvZmZzZXQiOjQwfQ==",
  "has_more": false,
  "limit": 20
}
```

Iterate with `next_cursor`/`has_more`. Invalid cursors yield `422`. Filtering in service layer supports `from`/`to` (ISO 8601) and `status` where available.

## Bulk operations (no `bulk` keyword)

All bulk node endpoints are now `bulk-first` without the `bulk` segment and return `BulkResult` (`{total,succeeded,failed,results}`) with `200` all-ok or `207 Multi-Status` partial; `422` when all fail (where applicable). Results are per-node with `status: "success"|"error"` and never roll back successful items.

| Action | Method & Path | Body | Success codes |
|--------|---------------|------|---------------|
| Bulk update | `PATCH /api/v2/nodes/` | `{"updates": [{"id": "<uuid>", "changes": {"tags": [...], "description": "...", "has_docker": true}}]}` (1..100) | `200` / `207` |
| Bulk delete | `POST /api/v2/nodes/deletions` | `{"ids": ["<uuid>", ...]}` (1..100) | `200` / `207` |
| Bulk check | `POST /api/v2/nodes/checks` | `{"ids": ["<uuid>", ...]}` (1..100) | `200` / `207` |
| Bulk metrics | `POST /api/v2/nodes/metrics` | `{"ids": ["<uuid>", ...]}` (1..100) | `200` / `207` |
| Bulk credential validations | `POST /api/v2/nodes/credential-validations` | `{"ids": ["<uuid>"], "tags": ["prod"]}` (ids or tags, 1..100) | `200` / `207` |

> Old paths removed: `POST /nodes/bulk/check`, `POST /nodes/bulk/tags/add`, `POST /nodes/bulk/tags/remove`, `POST /nodes/bulk/delete` (and `PATCH /nodes/bulk/update`). Tag bulk add/remove is now done via `PATCH /nodes/` with `changes.tags`. Fleet filtering by tags is only on `POST /nodes/credential-validations`.

### Bulk update (PATCH collection)

```bash
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": [
      {"id": "<id-1>", "changes": {"tags": ["production","frontend"], "description": "Updated"}},
      {"id": "<id-2>", "changes": {"has_docker": true, "docker_host": "unix:///var/run/docker.sock"}}
    ]
  }' \
  "${NODE_NEXUS_URL}/api/v2/nodes/"
  # 200 or 207
  # {"total":2,"succeeded":2,"failed":0,"results":[{"node_id":"<id-1>","status":"success"}, ...]}
```

### Bulk delete

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/deletions"
```

### Bulk check

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/checks"
```

### Bulk metrics

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/metrics"
  # results: [{node_id, node_name, status, metrics:{cpu,memory,disk,load_average,uptime_since}, error}]
```

### Bulk credential validations

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>"], "tags": ["production"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/credential-validations"
  # results: [{node_id, node_name, status:"success"|"error", message}]
```

All bulk responses use the unified `BulkResult` envelope; inspect each `results[]` entry for `status`/`error`. Single-node `ids=[id]` is the canonical way to operate on one node via bulk.

Use Swagger UI at `/docs` for the current request and response schemas.
