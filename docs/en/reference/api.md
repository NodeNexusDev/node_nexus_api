---
title: HTTP API
status: stable
translation_key: reference.api
source_revision: "2026-08-26"
---

# HTTP API

The base path is `/api/v2`. Requests and responses use JSON unless an endpoint
documents otherwise. Protected operations require `X-API-Key` or a JWT
`Authorization: Bearer` token. See [Authentication](../guides/authentication.md)
for details on both methods.

## API versioning

Clients may send an `X-API-Version` header. The only supported version is `1`;
missing header defaults to `1`. Unsupported versions return `400 Bad Request`.
`/health`, `/ready`, and `/metrics` ignore this header.

Runtime contract links:

- [Interactive API reference](openapi.html)
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

List endpoints use either `page`/`size` offset pagination or
`cursor`/`limit` keyset pagination. Rate limits are process-local and configured
through environment variables. The global request timeout returns `504`.
Validation errors use FastAPI's validation envelope; domain errors use
a stable JSON envelope with `code`, `message`, `request_id`, and `detail` fields
(see [Error catalog](error-catalog.md)).

```bash
curl -H 'X-API-Key: your-key' \
  'http://localhost:8000/api/v2/nodes/?page=1&size=20'
```

The complete endpoint and schema catalog is generated from routes and Pydantic
models. WebSocket frames are documented in the
[WebSocket guide](../guides/websocket.md).
