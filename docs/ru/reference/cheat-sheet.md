---
title: Шпаргалка
status: stable
translation_key: reference.cheat-sheet
source_revision: "2026-08-16"
---

# Шпаргалка

Готовые команды для типовых операций. Подставьте свои значения вместо
`${...}`.

## Настройка

```bash
export NODE_NEXUS_URL=http://localhost:8000
export NODE_NEXUS_API_KEY='your-key'
```

## Ноды

| Задача | Команда |
|--------|---------|
| Список нод | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/?page=1&size=20"` |
| Фильтр по тегам | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/?tags=production&tags=frontend"` |
| Создать ноду | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"srv","host":"192.0.2.10","port":22,"connection_type":"ssh","username":"ops","password":"...","tags":["prod"]}' "${NODE_NEXUS_URL}/api/v1/nodes/"` |
| Получить ноду | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Обновить ноду | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["prod","db"]}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Удалить ноду | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}"` |
| Проверить связь | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/check/"` |
| Валидация credentials | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"host":"192.0.2.10","port":22,"username":"ops","password":"..."}' "${NODE_NEXUS_URL}/api/v1/nodes/validate-credentials"` |
| Метрики | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/metrics/"` |

## Команды

| Задача | Команда |
|--------|---------|
| Выполнить команду | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"uptime"}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/execute/"` |
| На нескольких нодах | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"df -h","node_ids":["id1","id2"]}' "${NODE_NEXUS_URL}/api/v1/nodes/bulk/execute/"` |
| Создать шаблон | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"disk","command":"df -h {{ mount }}","parameters":[{"name":"mount","type":"string","required":true}]}' "${NODE_NEXUS_URL}/api/v1/commands/"` |
| Список шаблонов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/commands/?page=1&size=20"` |
| Выполнить шаблон | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d "{\"node_id\":\"${NODE_ID}\",\"params\":{\"mount\":\"/\"}}" "${NODE_NEXUS_URL}/api/v1/commands/${COMMAND_ID}/execute"` |

## Docker

| Задача | Команда |
|--------|---------|
| Список контейнеров | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/"` |
| Список образов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/images/"` |
| Exec в контейнере | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec/"` |
| Запустить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/start/"` |
| Остановить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stop/"` |

## Конфигурация

| Задача | Команда |
|--------|---------|
| Экспорт | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/config/export"` |
| Импорт | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v1/config/import"` |
| Dry-run импорт | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"dry_run":true,"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v1/config/import"` |

## API-ключи

| Задача | Команда |
|--------|---------|
| Создать ключ | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"reader","scope":"read-only"}' "${NODE_NEXUS_URL}/api/v1/api-keys/"` |
| Список ключей | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/api-keys/?page=1&size=20"` |
| Обновить ключ | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"is_active":false}' "${NODE_NEXUS_URL}/api/v1/api-keys/${KEY_ID}"` |
| Удалить ключ | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/api-keys/${KEY_ID}"` |

## Аудит

| Задача | Команда |
|--------|---------|
| События | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/audit/?page=1&size=50"` |
| Фильтр по ноде | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v1/audit/?node_id=${NODE_ID}"` |
| Удалить журнал | `curl -X DELETE -H "X-API-Key: ${MASTER_API_KEY}" "${NODE_NEXUS_URL}/api/v1/audit/?confirm=yes"` |

## Пробы

| Задача | Команда |
|--------|---------|
| Liveness | `curl "${NODE_NEXUS_URL}/health"` |
| Readiness | `curl "${NODE_NEXUS_URL}/ready"` |
| Метрики | `curl "${NODE_NEXUS_URL}/metrics"` |

Полный каталог endpoint'ов: [HTTP API](api.md). Схемы запросов и ответов:
[интерактивная документация](openapi.html).
