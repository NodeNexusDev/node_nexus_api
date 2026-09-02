---
title: Избранное, заметки и теги
status: stable
translation_key: guides.favorites-notes-tags
source_revision: "2026-09-02"
---

# Избранное, заметки и теги

Stage F добавляет лёгкие коллаборационные функции: избранное для быстрого
доступа, управление тегами и документирование нод через поле `description`.

> **Заметки удалены в 2.0:** `GET|POST /notes/{type}/{id}`, `PUT /notes/{id}`, `DELETE /notes/{id}` и таблица `notes` удалены (см. `MIGRATION.md`). Используйте `PATCH /api/v2/nodes/{id} {"description": "..."}` и `GET /api/v2/nodes/{id}` (поле `description`, до 1000 символов, nullable). У `commands`/`scripts` поле `description` уже было.

## Избранное (cursor-пагинация)

Отмечайте команды, скрипты или ноды как избранные. Список теперь возвращает `CursorPage` (`GET /favorites/ → {items,next_cursor,has_more}` не плоский список) — т.е. `{items, next_cursor, has_more, limit}`.

### Список избранных

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
```

Ответ:

```json
{
  "items": [
    {"id": "...", "target_type": "command", "target_id": "...", "name": "my-cmd", "note": "...", "created_at": "2026-09-02T10:00:00Z"}
  ],
  "next_cursor": "eyJvZmZzZXQiOjIwfQ==",
  "has_more": false,
  "limit": 20
}
```

Итерируйтесь через `next_cursor`/`has_more`. Невалидный курсор — `422`. Опциональный фильтр `?target_type=command|script|node`.

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites?target_type=command&limit=20"
```

### Добавить в избранное

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"target_type": "command", "target_id": "<command-id>"}' \
  "${NODE_NEXUS_URL}/api/v2/favorites"
  # 201 {id,target_type,target_id,name,note,created_at}
```

`target_type` — `command`, `script` или `node`. Опционально можно задать `name`/`note`.

### Удалить из избранного

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites/command/<command-id>"
  # 204 No Content
```

## Заметки — удалены в 2.0 → используйте PATCH /nodes/{id} {description}

Функция заметок удалена в 2.0 → используйте `PATCH /nodes/{id} {description}`. Не вызывайте:

- `GET /api/v2/notes/command/{id}`
- `POST /api/v2/notes/command/{id}`
- `PUT /api/v2/notes/{id}`
- `DELETE /api/v2/notes/{id}`

**Миграция:** храните документацию прямо в ноде:

```bash
  # было: POST /notes/node/<id> {"content": "..."}
  # стало:
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"description": "TODO: проверить параметры"}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>"
  # -> { ..., "description": "TODO: проверить..." }
```

У команд и скриптов уже есть собственное поле `description`.

## Управление тегами

Переименование или удаление тегов глобально. Переименование обновляет все
сущности, использующие этот тег.

### Переименовать тег

```bash
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"new_name": "production-ready"}' \
  "${NODE_NEXUS_URL}/api/v2/tags/old-tag-name"
```

### Удалить тег

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/tags/tag-to-delete"
```

## Клонирование

Клонирование команд и скриптов для создания копий.

### Клонировать команду

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/clone?new_name=my-copy"
  # 201
```

### Клонировать скрипт

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/clone?new_name=my-copy"
  # 201
```
