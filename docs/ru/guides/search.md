---
title: Global search
status: stable
translation_key: guides.search
source_revision: "2026-09-02"
---

# Global search

Unified search across nodes, commands, scripts, and tags. Backed by `app/adapters/persistence/global_search.py` via `GlobalSearchReader` port and `GlobalSearchService`.

## Endpoint

```http
GET /api/v2/search?q=deploy&limit=20
```

Query `q` is required (`min_length=1`). `limit` is `1..100`, default `20`. Requires authentication (`X-API-Key` or JWT).

## Response

```json
{
  "nodes": [{"id": "...", "name": "prod-web", "type": "node"}],
  "commands": [{"id": "...", "name": "deploy", "type": "command"}],
  "scripts": [{"id": "...", "name": "bootstrap", "type": "script"}],
  "tags": ["deploy", "prod"]
}
```

Each `SearchResultItem` contains `id`, `name`, `type`, and `score` (ranking). Tags are aggregated distinct values matching the query.

## Example

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'q=deploy' \
  "${NODE_NEXUS_URL}/api/v2/search"

curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'q=nginx' \
  --data-urlencode 'limit=5' \
  "${NODE_NEXUS_URL}/api/v2/search?limit=5"
```

## Notes

* Search is case-insensitive, `ILIKE` on `name`, `host`, `description`, and `tags`.
* `dashboard-search-metrics.md` also documents `GET /api/v2/search` alongside stats and SSE.

## See also

* `app/api/v2/search.py` — transport adapter
* `app/application/services/global_search_service.py` — use case
* `app/adapters/persistence/global_search.py` — SQL `UNION` implementation
