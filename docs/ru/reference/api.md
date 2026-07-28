---
title: HTTP API
status: stable
translation_key: reference.api
source_revision: "2026-07-29"
---

# HTTP API

Версионированный base path — `/api/v1`. Запросы и ответы используют JSON, если
endpoint не говорит иначе. Защищённым операциям нужен `X-API-Key`.

Runtime contract:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

Списки используют offset pagination `page`/`size` или keyset pagination
`cursor`/`limit`. Rate limits локальны для process и задаются environment
variables. Global request timeout возвращает `504`. Validation errors используют
FastAPI envelope, domain errors — `{"detail": "message"}`.

```bash
curl -H 'X-API-Key: your-key' \
  'http://localhost:8000/api/v1/nodes/?page=1&size=20'
```

Полный каталог endpoints и schemas генерируется из routes и Pydantic models.
WebSocket frames описаны в [руководстве](../guides/websocket.md).
