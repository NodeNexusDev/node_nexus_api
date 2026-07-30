---
title: Каталог ошибок
status: stable
translation_key: reference.error-catalog
source_revision: "2026-07-30"
---

# Каталог ошибок

| Status | Значение |
|---|---|
| `400` | Некорректный или неподдерживаемый request |
| `401` | API key отсутствует, невалиден, истёк или отозван |
| `403` | API key не имеет write scope |
| `404` | Node, command, script, container, image, tag или schedule не найден |
| `409` | Конфликт имени ноды |
| `422` | Ошибка schema, template, Docker, schedule, config format или domain validation |
| `429` | Превышен process-local rate limit |
| `502` | Ошибка удалённой Docker operation |
| `503` | Недоступен SSH connection, Docker daemon, credential decryption, audit persistence или scheduler |
| `504` | Global request timeout |

Domain failures используют стабильный JSON-конверт:

```json
{
    "code": "NodeNotFoundError",
    "message": "Node ... not found",
    "request_id": "req_abc123",
    "detail": "Node ... not found"
}
```

- `code` — machine-readable тип ошибки (имя класса domain exception)
- `message` — human-readable описание
- `request_id` — correlation id из request middleware (`null` если недоступен)
- `detail` — то же, что и `message`, для обратной совместимости

Клиентская логика должна опираться на HTTP status и `code`, а не на текст
`message` или `detail`.
