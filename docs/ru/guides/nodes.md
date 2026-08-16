---
title: Управление нодами
status: stable
translation_key: guides.nodes
source_revision: "2026-08-16"
---

# Управление нодами

Ноды — это удалённые серверы, доступные по SSH. Каждая нода хранит
зашифрованные учётные данные, метаданные подключения, теги и статус последней
проверки.

## Создание ноды

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v1/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "web-01",
    "host": "192.0.2.10",
    "port": 22,
    "connection_type": "ssh",
    "username": "ops",
    "password": "change-me",
    "tags": ["production", "frontend"]
  }'
```

Сохраните возвращённый UUID для метрик, выполнения команд и проверок
подключения.

## Валидация учётных данных

Проверьте SSH-подключение по предоставленным учётным данным без сохранения
ноды в базу данных. Полезно перед созданием ноды для проверки доступности.

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v1/nodes/validate-credentials" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "host": "192.0.2.10",
    "port": 22,
    "username": "ops",
    "password": "change-me"
  }'
```

Ответ:

```json
{
  "status": "active",
  "message": "SSH connection successful"
}
```

При ошибке подключения:

```json
{
  "status": "unreachable",
  "message": "Connection refused"
}
```

## Список и фильтрация

Offset-пагинация:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'page=1' \
  --data-urlencode 'size=20' \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

Фильтрация по тегам с логикой AND:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tags=production' \
  --data-urlencode 'tags=frontend' \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

Не смешивайте offset-пагинацию (`page`/`size`) и cursor-пагинацию
(`cursor`/`limit`) в одном запросе. Используйте `total` из ответа для
итерации страниц.

## Проверка подключения

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/check/"
```

Успешная проверка подтверждает доступность по SSH. Статус ноды обновляется
автоматически.

## Системные метрики

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/metrics/"
```

Возвращает информацию о CPU, памяти, дисках и нагрузке с удалённого хоста.

## История команд ноды

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/commands/history?page=1&size=20"
```

Возвращает пагинированный список выполненных команд на данной ноде. Каждая
запись содержит fingerprint команды, exit code, обрезанные stdout/stderr с
оригинальными byte count, а также время выполнения. Вывод ограничивается
политикой `bound_output()` для защиты от переполнения.

## История статусов

Запросите историю изменений статуса (active/unreachable/error) для ноды:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/status-history?page=1&size=50"
```

Необязательные параметры: `from` и `to` (ISO 8601), `status` (например,
`active`, `unreachable`). Возвращает пагинированный список записей с
`previous_status`, `new_status`, `reason` и `changed_at`.

История записывается автоматически при проверке подключения или обновлении ноды.

## Массовые операции

Выполнение массовых действий на нескольких нодах одновременно.

### Массовая проверка связи

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v1/nodes/bulk/check"
```

### Массовое добавление тегов

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>"], "tags": ["staging"]}' \
  "${NODE_NEXUS_URL}/api/v1/nodes/bulk/tags/add"
```

### Массовое удаление тегов

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>"], "tags": ["deprecated"]}' \
  "${NODE_NEXUS_URL}/api/v1/nodes/bulk/tags/remove"
```

### Массовое удаление нод

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v1/nodes/bulk/delete"
```

Все массовые endpoint'ы принимают `node_ids` и/или `node_tags` (пересечение AND).
Ответ содержит `success`/`error` по каждой ноде.

Актуальные схемы запросов и ответов смотрите в Swagger UI (`/docs`).
