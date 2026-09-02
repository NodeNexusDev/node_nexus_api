---
title: HTTP API
status: stable
translation_key: reference.api
source_revision: "2026-09-02"
---

# HTTP API

The base path is `/api/v2` (version `2.0.0`). Requests and responses use JSON unless an endpoint
documents otherwise. Protected operations require `X-API-Key` or a JWT
`Authorization: Bearer` token. See [Authentication](../guides/authentication.md)
for details on both methods.

Runtime contract links:

- [Interactive API reference](openapi.html)
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

List endpoints use `cursor`/`limit` keyset pagination. The cursor is an opaque
base64 token; `limit` is 1–100 (default 20). Responses use
`{items, next_cursor, has_more, limit}` — `total` is omitted (COUNT(*) expensive).
Use `has_more` + `next_cursor` to paginate.

Bulk endpoints are bulk-first and return `BulkResult` with
`{total, succeeded, failed, results}`. Status is `200` when all succeed,
`207 Multi-Status` when partially succeeded (`succeeded>0 && failed>0`), and
`422` when all failed. Each result has `status: "success" | "error"` plus
`error` / `output` when relevant. Single-item operations use `ids=[id]`.

Rate limits are process-local and configured
through environment variables. The global request timeout returns `504`.
Validation errors use FastAPI's validation envelope; domain errors use
a stable JSON envelope with `code`, `message`, `request_id`, and `detail` fields
(see [Error catalog](error-catalog.md)).

```bash
curl -H 'X-API-Key: your-key' \
  'http://localhost:8000/api/v2/nodes/?cursor=&limit=20'
```

The complete endpoint and schema catalog is generated from routes and Pydantic
models. WebSocket frames are documented in the
[WebSocket guide](../guides/websocket.md).
