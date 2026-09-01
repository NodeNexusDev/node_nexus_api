---
title: Шпаргалка
status: stable
translation_key: reference.cheat-sheet
source_revision: "2026-08-25"
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
| Список нод | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/?page=1&size=20"` |
| Фильтр по тегам | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/?tags=production&tags=frontend"` |
| Создать ноду | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"srv","host":"192.0.2.10","port":22,"connection_type":"ssh","username":"ops","password":"...","tags":["prod"]}' "${NODE_NEXUS_URL}/api/v2/nodes/"` |
| Создать ноду (SSH ключ) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"srv","host":"192.0.2.10","port":22,"connection_type":"ssh","username":"ops","ssh_key":"<ключ>","passphrase":"<пароль>"}' "${NODE_NEXUS_URL}/api/v2/nodes/"` |
| Получить ноду | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Обновить ноду | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["prod","db"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Удалить ноду | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Проверить связь | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/check/"` |
| Валидация credentials | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"host":"192.0.2.10","port":22,"username":"ops","password":"..."}' "${NODE_NEXUS_URL}/api/v2/nodes/validate-credentials"` |
| Валидация (SSH ключ) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"host":"192.0.2.10","port":22,"username":"ops","ssh_key":"<ключ>","passphrase":"<пароль>"}' "${NODE_NEXUS_URL}/api/v2/nodes/validate-credentials"` |
| Метрики | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/metrics/"` |
| История статусов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/status-history?page=1&size=50"` |
| Массовая проверка | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/bulk/check"` |
| Массовое добавление тегов | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>"],"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v2/nodes/bulk/tags/add"` |
| Массовое удаление тегов | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>"],"tags":["deprecated"]}' "${NODE_NEXUS_URL}/api/v2/nodes/bulk/tags/remove"` |
| Массовое удаление нод | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"node_ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/bulk/delete"` |

## Команды

| Задача | Команда |
|--------|---------|
| Выполнить команду | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"uptime"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/execute/"` |
| На нескольких нодах | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"df -h","node_ids":["id1","id2"]}' "${NODE_NEXUS_URL}/api/v2/nodes/bulk/execute/"` |
| Создать шаблон | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"disk","command":"df -h {{ mount }}","parameters":[{"name":"mount","type":"string","required":true}]}' "${NODE_NEXUS_URL}/api/v2/commands/"` |
| Список шаблонов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/?page=1&size=20"` |
| Выполнить шаблон | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d "{\"node_id\":\"${NODE_ID}\",\"params\":{\"mount\":\"/\"}}" "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/execute"` |
| Повтор команды | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/commands/${EXECUTION_ID}/retry"` |

## Docker

### Контейнеры

| Задача | Команда |
|--------|---------|
| Список контейнеров | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/"` |
| Список всех (вкл. остановленные) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?all=true"` |
| Создать контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","name":"my-ctr","command":"sleep 60"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers"` |
| Инспекция контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Запустить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/start/"` |
| Остановить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stop/"` |
| Перезапустить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/restart/"` |
| Приостановить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/pause/"` |
| Возобновить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/unpause/"` |
| Exec в контейнере | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec/"` |
| Логи контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/logs?tail=100"` |
| Статистика контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stats"` |
| Top контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/top"` |
| Удалить контейнер | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Очистить контейнеры | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"` |

### Images

| Задача | Команда |
|--------|---------|
| Список images | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/"` |
| Pull image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","timeout":120}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/pull"` |
| Инспекция image | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| Тег image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"repo":"local/alpine","tag":"v1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/tag"` |
| Удалить image | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| Очистить images | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/prune"` |

### Сети

| Задача | Команда |
|--------|---------|
| Список сетей | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks"` |
| Создать сеть | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-net","driver":"bridge"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks"` |
| Инспекция сети | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |
| Подключить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/connect"` |
| Отключить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/disconnect"` |
| Удалить сеть | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |

### Volumes

| Задача | Команда |
|--------|---------|
| Список volumes | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes"` |
| Создать volume | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-vol","driver":"local"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes"` |
| Инспекция volume | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Удалить volume | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Очистить volumes | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/prune"` |

### Система

| Задача | Команда |
|--------|---------|
| Информация о Docker | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/info"` |
| Использование диска | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/df"` |

## Скрипты

| Задача | Команда |
|--------|---------|
| Повтор скрипта | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/executions/${EXECUTION_ID}/retry"` |
| Отмена выполнения | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/executions/${EXECUTION_ID}/cancel"` |
| История расписаний | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/schedule/history?page=1&size=20"` |

## Конфигурация

| Задача | Команда |
|--------|---------|
| Экспорт | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/config/export"` |
| Импорт | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v2/config/import"` |
| Dry-run импорт | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"dry_run":true,"nodes":[...],"commands":[...]}' "${NODE_NEXUS_URL}/api/v2/config/import"` |

## API-ключи

| Задача | Команда |
|--------|---------|
| Создать ключ | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"reader","scope":"read-only"}' "${NODE_NEXUS_URL}/api/v2/api-keys/"` |
| Список ключей | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/api-keys/?page=1&size=20"` |
| Обновить ключ | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"is_active":false}' "${NODE_NEXUS_URL}/api/v2/api-keys/${KEY_ID}"` |
| Удалить ключ | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/api-keys/${KEY_ID}"` |

## Аудит

| Задача | Команда |
|--------|---------|
| События | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?page=1&size=50"` |
| Фильтр по ноде | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?node_id=${NODE_ID}"` |
| Удалить журнал | `curl -X DELETE -H "X-API-Key: ${MASTER_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?confirm=yes"` |
| Экспорт CSV | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/export?fmt=csv"` |

## Дашборд и поиск

| Задача | Команда |
|--------|---------|
| Обзор дашборда | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/dashboard/"` |
| Метрики дашборда | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/dashboard/metrics?group_by=day"` |
| Глобальный поиск | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/search?q=deploy"` |

## Статистика выполнения

| Задача | Команда |
|--------|---------|
| Статистика команды | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${CMD_ID}/stats"` |
| Статистика скрипта | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/stats"` |
| Статистика ноды | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/stats"` |

## Теги нод

| Задача | Команда |
|--------|---------|
| Список тегов нод | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/tags"` |
| Добавить теги | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/tags"` |
| Удалить теги | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["staging"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/tags"` |

## SSE поток событий

| Задача | Команда |
|--------|---------|
| Подписка на события | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/events/stream"` |

## Управление тегами

| Задача | Команда |
|--------|---------|
| Переименовать тег | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"new_name":"new-tag"}' "${NODE_NEXUS_URL}/api/v2/tags/old-tag"` |
| Удалить тег | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/tags/tag-to-delete"` |

## Клонирование

| Задача | Команда |
|--------|---------|
| Клонировать команду | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${CMD_ID}/clone?new_name=my-copy"` |
| Клонировать скрипт | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/clone?new_name=my-copy"` |

## Избранное

| Задача | Команда |
|--------|---------|
| Список избранного | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/favorites"` |
| Добавить в избранное | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"target_type":"command","target_id":"${CMD_ID}"}' "${NODE_NEXUS_URL}/api/v2/favorites"` |
| Удалить из избранного | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/favorites/command/${CMD_ID}"` |

## Заметки

| Задача | Команда |
|--------|---------|
| Список заметок | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/notes/command/${CMD_ID}"` |
| Создать заметку | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"content":"TODO: review"}' "${NODE_NEXUS_URL}/api/v2/notes/command/${CMD_ID}"` |
| Обновить заметку | `curl -X PUT -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"content":"Обновлено"}' "${NODE_NEXUS_URL}/api/v2/notes/${NOTE_ID}"` |
| Удалить заметку | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/notes/${NOTE_ID}"` |

## Пробы

| Задача | Команда |
|--------|---------|
| Liveness | `curl "${NODE_NEXUS_URL}/health"` |
| Readiness | `curl "${NODE_NEXUS_URL}/ready"` |
| Метрики | `curl "${NODE_NEXUS_URL}/metrics"` |

Полный каталог endpoint'ов: [HTTP API](api.md). Схемы запросов и ответов:
[интерактивная документация](openapi.html).
