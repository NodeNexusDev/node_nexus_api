---
title: Favorites, notes, and tags
status: stable
translation_key: guides.favorites-notes-tags
source_revision: "2026-09-02"
---

# Favorites, notes, and tags

Stage F adds lightweight collaboration features: favorites for quick access,
tag management across all entities, and node inline documentation via `description`.

> **Notes removed in 2.0:** `GET|POST /notes/{type}/{id}`, `PUT /notes/{id}`, `DELETE /notes/{id}` and the `notes` table were removed (see `MIGRATION.md`). Use `PATCH /api/v2/nodes/{id} {"description": "..."}` and `GET /api/v2/nodes/{id}` (`description` field, max 1000, nullable). `commands`/`scripts` already have `description`.

## Favorites (cursor pagination)

Mark commands, scripts, or nodes as favorites for quick access. Listing now uses `CursorPage` (`GET /favorites/ → {items,next_cursor,has_more}` not plain list) — i.e., `{items, next_cursor, has_more, limit}`.

### List favorites

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
```

Response:

```json
{
  "items": [
    {"id": "...", "target_type": "command", "target_id": "...", "name": "my-cmd", "note": "...", "created_at": "2026-09-02T10:00:00Z"}
  ],
  "next_cursor": "eyJvZmZzZXQiOjIwfQ==",
  "has_more": false,
  "limit": 20
}
```

Iterate with `next_cursor`/`has_more`. Invalid cursor → `422`. Optional filter `?target_type=command|script|node`.

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites?target_type=command&limit=20"
```

### Add a favorite

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"target_type": "command", "target_id": "<command-id>"}' \
  "${NODE_NEXUS_URL}/api/v2/favorites"
  # 201 {id,target_type,target_id,name,note,created_at}
```

`target_type` must be one of `command`, `script`, or `node`. Optional `name`/`note` can be set.

### Remove a favorite

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites/command/<command-id>"
```

Returns `204 No Content` on success.

## Notes — removed in 2.0 → use PATCH /nodes/{id} {description}

The notes feature was removed in 2.0 → use `PATCH /nodes/{id} {description}`. Do not call:

- `GET /api/v2/notes/command/{id}`
- `POST /api/v2/notes/command/{id}`
- `PUT /api/v2/notes/{id}`
- `DELETE /api/v2/notes/{id}`

**Migration:** store inline documentation in the node itself:

```bash
  # was: POST /notes/node/<id> {"content": "..."}
  # now:
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"description": "TODO: review parameters before production"}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>"
  # -> { ..., "description": "TODO: review..." }
```

`commands` and `scripts` already have their own `description` field.

## Tag management

Rename or delete tags globally. Renaming updates all nodes, commands, and scripts
that use the tag.

### Rename a tag

```bash
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"new_name": "production-ready"}' \
  "${NODE_NEXUS_URL}/api/v2/tags/old-tag-name"
```

### Delete a tag

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/tags/tag-to-delete"
```

Deleting a tag removes it from all entities. The entities themselves are not
deleted.

## Cloning

Clone commands and scripts to create copies with a new name.

### Clone a command

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/clone?new_name=my-disk-usage"
  # 201
```

### Clone a script

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/clone?new_name=my-deploy"
  # 201
```

The cloned entity retains the same parameters, tags, and steps. The clone
gets a new UUID and the specified name.
