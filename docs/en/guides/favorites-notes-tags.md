---
title: Favorites, notes, and tags
status: stable
translation_key: guides.favorites-notes-tags
source_revision: "2026-08-17"
---

# Favorites, notes, and tags

Stage F adds lightweight collaboration features: favorites for quick access,
notes for inline documentation, and tag management across all entities.

## Favorites

Mark commands, scripts, or nodes as favorites for quick access.

### List favorites

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/favorites"
```

Returns all favorites for the current key, ordered by creation time.

### Add a favorite

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"target_type": "command", "target_id": "<command-id>"}' \
  "${NODE_NEXUS_URL}/api/v1/favorites"
```

`target_type` must be one of `command`, `script`, or `node`.

### Remove a favorite

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/favorites/command/<command-id>"
```

Returns `204 No Content` on success.

## Notes

Attach notes to commands, scripts, or nodes for inline documentation.

### List notes for an entity

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/notes/command/<command-id>"
```

Returns all notes for the target, ordered by creation time.

### Create a note

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"content": "TODO: review parameters before production"}' \
  "${NODE_NEXUS_URL}/api/v1/notes/command/<command-id>"
```

### Update a note

```bash
curl --fail-with-body -X PUT \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"content": "Updated: parameters reviewed and approved"}' \
  "${NODE_NEXUS_URL}/api/v1/notes/<note-id>"
```

### Delete a note

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/notes/<note-id>"
```

Returns `204 No Content` on success.

## Tag management

Rename or delete tags globally. Renaming updates all nodes, commands, and scripts
that use the tag.

### Rename a tag

```bash
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"new_name": "production-ready"}' \
  "${NODE_NEXUS_URL}/api/v1/tags/old-tag-name"
```

### Delete a tag

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/tags/tag-to-delete"
```

Deleting a tag removes it from all entities. The entities themselves are not
deleted.

## Cloning

Clone commands and scripts to create copies with a new name.

### Clone a command

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/commands/<command-id>/clone?new_name=my-disk-usage"
```

### Clone a script

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script-id>/clone?new_name=my-deploy"
```

The cloned entity retains the same parameters, tags, and steps. The clone
gets a new UUID and the specified name.
