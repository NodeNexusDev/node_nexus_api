---
title: Избранное, заметки и теги
status: stable
translation_key: guides.favorites-notes-tags
source_revision: "2026-08-17"
---

# Избранное, заметки и теги

Stage F добавляет лёгкие коллаборационные функции: избранное для быстрого
доступа, заметки для документирования и управление тегами.

## Избранное

Отмечайте команды, скрипты или ноды как избранные для быстрого доступа.

### Список избранных

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites"
```

### Добавить в избранное

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"target_type": "command", "target_id": "<command-id>"}' \
  "${NODE_NEXUS_URL}/api/v2/favorites"
```

`target_type` — `command`, `script` или `node`.

### Удалить из избранного

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/favorites/command/<command-id>"
```

## Заметки

Прикрепляйте заметки к командам, скриптам или нодам.

### Список заметок

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/notes/command/<command-id>"
```

### Создать заметку

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"content": "TODO: проверить параметры"}' \
  "${NODE_NEXUS_URL}/api/v2/notes/command/<command-id>"
```

### Обновить заметку

```bash
curl --fail-with-body -X PUT \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"content": "Обновлено: параметры проверены"}' \
  "${NODE_NEXUS_URL}/api/v2/notes/<note-id>"
```

### Удалить заметку

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/notes/<note-id>"
```

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
```

### Клонировать скрипт

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script-id>/clone?new_name=my-copy"
```
