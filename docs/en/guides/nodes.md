---
title: Manage nodes
status: stable
translation_key: guides.nodes
source_revision: "2026-08-16"
---

# Manage nodes

Nodes represent remote servers reachable over SSH. Each node stores an encrypted
credential, connectivity metadata, tags, and a last-checked status.

## Create a node

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "web-01",
    "host": "192.0.2.10",
    "port": 22,
    "connection_type": "ssh",
    "username": "ops",
    "password": "change-me",
    "tags": ["production", "frontend"]
  }'
```

Save the returned UUID for metrics, command execution, and connectivity checks.

### SSH key authentication

Instead of a password, pass the private key content in `ssh_key`. If the key
is encrypted, supply the passphrase:

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "web-02",
    "host": "192.0.2.11",
    "port": 22,
    "connection_type": "ssh",
    "username": "ops",
    "ssh_key": "<private-key-content>",
    "passphrase": "key-passphrase"
  }'
```

`passphrase` is optional and only required when the SSH private key is
encrypted. Both `password`, `ssh_key`, and `passphrase` are encrypted at
rest and never returned in API responses.

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

## List and filter

Offset pagination:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'page=1' \
  --data-urlencode 'size=20' \
  "${NODE_NEXUS_URL}/api/v2/nodes/"
```

Filter by tags with AND matching:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tags=production' \
  --data-urlencode 'tags=frontend' \
  "${NODE_NEXUS_URL}/api/v2/nodes/"
```

Do not mix offset (`page`/`size`) and cursor (`cursor`/`limit`) pagination in
the same request. Use `total` from the response to iterate pages.

## Verify connectivity

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/check/"
```

A successful check confirms SSH reachability. The node status is updated
automatically.

## System metrics

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/metrics/"
```

Returns CPU, memory, disk, and load information from the remote host.

## Command history

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/commands/history?page=1&size=20"
```

Returns a paginated list of commands executed on this node. Each record contains
the command fingerprint, exit code, truncated stdout/stderr with original byte
counts, and execution time. Output is bounded by the `bound_output()` policy to
prevent unbounded growth.

## Status history

Query the history of status changes (active/unreachable/error) for a node:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/status-history?page=1&size=50"
```

Optional query parameters: `from` and `to` (ISO 8601 timestamps), `status`
(e.g. `active`, `unreachable`). Returns a paginated list of status change records
with `previous_status`, `new_status`, `reason`, and `changed_at`.

Status changes are recorded automatically when you run connectivity checks or
update a node.

## Bulk operations

Perform bulk actions on multiple nodes at once.

### Bulk check connectivity

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/bulk/check"
```

### Bulk add tags

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>"], "tags": ["staging"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/bulk/tags/add"
```

### Bulk remove tags

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>"], "tags": ["deprecated"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/bulk/tags/remove"
```

### Bulk delete

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/bulk/delete"
```

All bulk endpoints accept `node_ids` and/or `node_tags` (AND intersection).
Each response contains per-node `success`/`error` entries.

Use Swagger UI at `/docs` for the current request and response schemas.
