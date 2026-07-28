---
title: Каталог ошибок
status: stable
translation_key: reference.error-catalog
source_revision: "2026-07-29"
---

# Каталог ошибок

| Status | Значение |
|---|---|
| `400` | Некорректный или неподдерживаемый request |
| `401` | API key отсутствует, невалиден, истёк или отозван |
| `403` | API key не имеет write scope |
| `404` | Node, command, script, container, image или tag не найден |
| `409` | Конфликт имени ноды |
| `422` | Ошибка schema, template, Docker или domain validation |
| `429` | Превышен process-local rate limit |
| `502` | Ошибка удалённой Docker operation |
| `503` | Недоступен SSH connection или Docker daemon |
| `504` | Global request timeout |

Domain failures используют `{"detail": "message"}`. Клиентская логика должна
опираться на HTTP status и schemas, а не на текст сообщения.
