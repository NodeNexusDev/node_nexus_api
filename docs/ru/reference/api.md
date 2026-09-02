---
title: HTTP API
status: stable
translation_key: reference.api
source_revision: "2026-09-02"
---

# HTTP API

Base path — `/api/v2` (версия `2.0.0`). Запросы и ответы используют JSON, если endpoint не
говорит иначе. Защищённым операциям нужен `X-API-Key` или JWT
`Authorization: Bearer` токен. Подробности обоих методах см. в
[руководстве по аутентификации](../guides/authentication.md).

Runtime contract:

- [Интерактивный справочник API](openapi.html)
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

Списки используют keyset pagination `cursor`/`limit`. Курсор — opaque base64
токен; `limit` 1–100 (default 20). Ответы — `{items, next_cursor, has_more, limit}`,
`total` отсутствует (COUNT(*) дорого). Используйте `has_more` + `next_cursor` для пагинации.

Bulk endpoints работают в bulk-first режиме и возвращают `BulkResult`
`{total, succeeded, failed, results}`. Статус `200` — все успешно,
`207 Multi-Status` — частично успешно (`succeeded>0 && failed>0`), `422` —
все неуспешно. Каждый результат имеет `status: "success" | "error"` и поля
`error` / `output` при необходимости. Одиночные операции — `ids=[id]`.

Rate limits локальны для process и задаются environment
variables. Global request timeout возвращает `504`. Validation errors используют
FastAPI envelope, domain errors —
стабильный JSON-конверт с полями `code`, `message`, `request_id` и `detail`
(см. [Каталог ошибок](error-catalog.md)).

```bash
curl -H 'X-API-Key: your-key' \
  'http://localhost:8000/api/v2/nodes/?cursor=&limit=20'
```

Полный каталог endpoints и schemas генерируется из routes и Pydantic models.
WebSocket frames описаны в [руководстве](../guides/websocket.md).
