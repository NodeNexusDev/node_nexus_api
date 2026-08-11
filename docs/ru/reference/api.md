---
title: HTTP API
status: stable
translation_key: reference.api
source_revision: "2026-07-30"
---

# HTTP API

Base path — `/api/v1`. Запросы и ответы используют JSON, если endpoint не
говорит иначе. Защищённым операциям нужен `X-API-Key`.

## Версионирование API

Клиенты могут отправлять заголовок `X-API-Version`. Поддерживаемая версия —
`1`; отсутствие заголовка трактуется как `1`. Неподдерживаемые версии
возвращают `400 Bad Request`. Endpoints `/health`, `/ready` и `/metrics`
игнорируют этот заголовок.

Runtime contract:

- [Интерактивный справочник API](openapi.html)
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

Списки используют offset pagination `page`/`size` или keyset pagination
`cursor`/`limit`. Rate limits локальны для process и задаются environment
variables. Global request timeout возвращает `504`. Validation errors используют
FastAPI envelope, domain errors —
стабильный JSON-конверт с полями `code`, `message`, `request_id` и `detail`
(см. [Каталог ошибок](error-catalog.md)).

```bash
curl -H 'X-API-Key: your-key' \
  'http://localhost:8000/api/v1/nodes/?page=1&size=20'
```

Полный каталог endpoints и schemas генерируется из routes и Pydantic models.
WebSocket frames описаны в [руководстве](../guides/websocket.md).
