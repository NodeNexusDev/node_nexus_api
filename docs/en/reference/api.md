---
title: HTTP API
status: stable
translation_key: reference.api
source_revision: "2026-07-29"
---

# HTTP API

The versioned base path is `/api/v1`. Requests and responses use JSON unless an
endpoint documents otherwise. Protected operations require `X-API-Key`.

Runtime contract links:

- [Interactive API reference](openapi.html)
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

List endpoints use either `page`/`size` offset pagination or
`cursor`/`limit` keyset pagination. Rate limits are process-local and configured
through environment variables. The global request timeout returns `504`.
Validation errors use FastAPI's validation envelope; domain errors use
`{"detail": "message"}`.

```bash
curl -H 'X-API-Key: your-key' \
  'http://localhost:8000/api/v1/nodes/?page=1&size=20'
```

The complete endpoint and schema catalog is generated from routes and Pydantic
models. WebSocket frames are documented in the
[WebSocket guide](../guides/websocket.md).
