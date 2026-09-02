---
title: Шпаргалка
status: stable
translation_key: reference.cheat-sheet
source_revision: "2026-09-02"
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
| Список нод | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/?cursor=&limit=20"` |
| Фильтр по тегам | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/?tags=production&tags=frontend"` |
| Массовое создание нод | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"items": [{"name":"srv","host":"192.0.2.10","port":22,"connection_type":"ssh","username":"ops","password":"...","tags":["prod"]}]}' "${NODE_NEXUS_URL}/api/v2/nodes/"` |
| Получить ноду | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Обновить одну ноду | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"tags":["prod","db"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Массовое обновление нод | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"updates": [{"id":"${NODE_ID}","changes":{"tags":["prod","db"]}}]}' "${NODE_NEXUS_URL}/api/v2/nodes/"` |
| Удалить ноду | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"` |
| Массовое удаление нод | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/deletions"` |
| Массовая проверка | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/checks"` |
| Массовые метрики | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>","<id2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/metrics"` |
| Массовая валидация credentials | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"ids":["<id1>"],"tags":["prod"]}' "${NODE_NEXUS_URL}/api/v2/nodes/credential-validations"` |
| История статусов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/status-history?cursor=&limit=20"` |

Bulk ответы — `BulkResult` `{total,succeeded,failed,results}` с кодами `200` все ок, `207` частично, `422` все неуспешно.

## Команды

| Задача | Команда |
|--------|---------|
| Массовое создание команд | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"items": [{"name":"disk","command":"df -h {{ mount }}","parameters":[{"name":"mount","type":"string","required":true}]}]}' "${NODE_NEXUS_URL}/api/v2/commands/"` |
| Список шаблонов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/?cursor=&limit=20"` |
| Получить команду | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}"` |
| Обновить команду | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"description":"updated"}' "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}"` |
| Удалить команду | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}"` |
| Выполнить команды на нодах (M×N) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command_ids":["<cmd1>"],"node_ids":["<id1>","<id2>"],"node_tags":[],"params":{"<cmd1>":{"mount":"/"}}}' "${NODE_NEXUS_URL}/api/v2/commands/executions"` |
| Выполнить сырые команды (M×N) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"commands":["uptime","df -h"],"node_ids":["<id1>"]}' "${NODE_NEXUS_URL}/api/v2/commands/raw-executions"` |
| История команд | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/history?node_id=${NODE_ID}&cursor=&limit=20"` |
| История выполнений | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/executions/history?batch_id=${BATCH_ID}&cursor=&limit=20"` |
| Массовый retry | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"execution_ids":["<exec1>"]}' "${NODE_NEXUS_URL}/api/v2/commands/executions/retries"` |
| Массовая отмена | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"execution_ids":["<exec1>"]}' "${NODE_NEXUS_URL}/api/v2/commands/executions/cancels"` |

## Docker

### Контейнеры

| Задача | Команда |
|--------|---------|
| Список контейнеров | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/?cursor=&limit=20"` |
| Список всех (вкл. остановленные) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?all=true&cursor=&limit=20"` |
| Создать контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","name":"my-ctr","command":"sleep 60"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers"` |
| Инспекция контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Запустить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/start"` |
| Остановить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stop?timeout=10"` |
| Перезапустить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/restart?timeout=10"` |
| Приостановить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/pause"` |
| Возобновить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/unpause"` |
| Kill контейнера | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"signal":"SIGKILL"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/kill"` |
| Обновить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"memory":"512m","cpus":"1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/update"` |
| Exec в контейнере | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec"` |
| Логи контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/logs?tail=100"` |
| Статистика контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stats"` |
| Top контейнера | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/top"` |
| Get archive | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/etc/hosts"` |
| Put archive | `curl -X PUT -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/tmp/data"` |
| Port | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/port?private_port=80"` |
| Wait | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/wait?timeout=30"` |
| Удалить контейнер | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"` |
| Очистить контейнеры | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"` |
| Массовый старт | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>","<cid2>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/starts"` |
| Массовая остановка | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/stops?timeout=10"` |
| Массовый рестарт | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/restarts?timeout=10"` |
| Массовое удаление | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/removals?force=false"` |
| Массовая пауза | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/pauses"` |
| Массовое возобновление | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/unpauses"` |
| Массовый kill | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"],"signal":"SIGKILL"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/kills"` |
| Массовое обновление | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"],"memory":"512m","cpus":"1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/updates"` |
| Массовые executions | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>","<cid2>"],"command":"id","timeout":30}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/executions"` |
| Массовые inspections | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/inspections"` |
| Массовые логи | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"],"tail":100}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/logs"` |
| Массовая статистика | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_ids":["<cid1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/stats"` |

### Images

| Задача | Команда |
|--------|---------|
| Список images | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/?cursor=&limit=20"` |
| Pull image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest","timeout":120}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/pull"` |
| Build image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"dockerfile":"FROM alpine","tag":"my:1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/build"` |
| Массовые pulls | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"images":["alpine:latest"],"timeout":120}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/pulls"` |
| Массовые removals | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image_ids":["alpine:latest"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/removals"` |
| Инспекция image | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| История image | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/history"` |
| Тег image | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"repo":"local/alpine","tag":"v1.0"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/tag"` |
| Push image (path) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/push"` |
| Push image (body) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"image":"alpine:latest"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/push"` |
| Удалить image | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"` |
| Очистить images | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/prune"` |

### Сети

| Задача | Команда |
|--------|---------|
| Список сетей | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks?cursor=&limit=20"` |
| Создать сеть | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-net","driver":"bridge"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks"` |
| Инспекция сети | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |
| Массовые removals | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"network_ids":["<net1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/removals"` |
| Очистить сети | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/prune"` |
| Подключить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/connect"` |
| Отключить контейнер | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"container_id":"${CONTAINER_ID}"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/disconnect"` |
| Удалить сеть | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"` |

### Volumes

| Задача | Команда |
|--------|---------|
| Список volumes | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes?cursor=&limit=20"` |
| Создать volume | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"name":"my-vol","driver":"local"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes"` |
| Инспекция volume | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Массовые removals | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"volume_names":["<vol1>"]}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/removals"` |
| Удалить volume | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"` |
| Очистить volumes | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/prune"` |

### Система

| Задача | Команда |
|--------|---------|
| Информация о Docker | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/info"` |
| Версия Docker | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/version"` |
| Использование диска | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/df"` |
| System prune | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/prune?volumes=false"` |
| Очистить контейнеры | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"` |
| Очистить images | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/prune"` |

## Compose

| Задача | Команда |
|--------|---------|
| Создать compose проект | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"project_name":"myapp","compose":"services:\n  web:\n    image: nginx"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects"` |
| Список compose проектов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects?cursor=&limit=20"` |
| Получить проект | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}"` |
| Обновить проект | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"compose":"services:\n  web:\n    image: nginx:1.25"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}"` |
| Удалить проект | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}"` |
| Compose up | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"pull":true}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/ups"` |
| Compose down | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"volumes":false}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/downs"` |
| Compose ps | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/ps"` |
| Compose логи | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/logs?tail=100"` |
| Compose config | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/config"` |
| Compose exec | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"service":"web","command":"ls"}' "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/compose/projects/${PROJECT}/executions"` |

## Templates

| Задача | Команда |
|--------|---------|
| Создать registry | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"owner":"myorg","name":"templates","default_branch":"main"}' "${NODE_NEXUS_URL}/api/v2/templates/registries"` |
| Список registries | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/registries?cursor=&limit=20"` |
| Синхронизировать registry | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/registries/${REGISTRY_ID}/syncs"` |
| Создать pack (локально) | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"manifest":{"pack_id":"my-pack","name":"My Pack","version":"1.0.0"},"commands":[],"scripts":[]}' "${NODE_NEXUS_URL}/api/v2/templates/packs"` |
| Список packs | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs?cursor=&limit=20"` |
| Получить pack | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}"` |
| Архив pack | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/archive" --output pack.tar` |
| Установить pack | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?on_conflict=fail"` |
| Удалить установку | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/uninstallations"` |
| Обновить pack | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/updates?on_conflict=fail"` |
| Список установок | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/templates/packs/${PACK_ID}/installations?cursor=&limit=20"` |

## Скрипты

| Задача | Команда |
|--------|---------|
| Массовое создание скриптов | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"items": [{"name":"deploy","steps":[{"command":"uptime"}]}]}' "${NODE_NEXUS_URL}/api/v2/scripts/"` |
| Список скриптов | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/?cursor=&limit=20"` |
| Повтор скрипта | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/executions/${EXECUTION_ID}/retry"` |
| Отмена выполнения | `curl -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/executions/${EXECUTION_ID}/cancel"` |
| История расписаний | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/schedule/history?cursor=&limit=20"` |

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
| Список ключей | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/api-keys/?cursor=&limit=20"` |
| Обновить ключ | `curl -X PATCH -H "X-API-Key: ${NODE_NEXUS_API_KEY}" -H 'Content-Type: application/json' -d '{"is_active":false}' "${NODE_NEXUS_URL}/api/v2/api-keys/${KEY_ID}"` |
| Удалить ключ | `curl -X DELETE -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/api-keys/${KEY_ID}"` |

## Аудит

| Задача | Команда |
|--------|---------|
| События | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?cursor=&limit=20"` |
| Фильтр по ноде | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?node_id=${NODE_ID}"` |
| Статистика аудита | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats"` |
| Удалить журнал | `curl -X DELETE -H "X-API-Key: ${MASTER_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?confirm=yes"` |
| Экспорт CSV | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/export?fmt=csv"` |

## Поиск

| Задача | Команда |
|--------|---------|
| Глобальный поиск | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/search?q=deploy"` |

## Статистика выполнения

| Задача | Команда |
|--------|---------|
| Статистика команд (snapshot) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/stats"` |
| Статистика команд (buckets) | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/stats?group_by=day"` |
| Статистика команды | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/commands/${CMD_ID}/stats"` |
| Статистика скрипта | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/stats"` |
| Статистика ноды | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/stats"` |
| Статистика всех нод | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/stats?group_by=day"` |
| Статистика аудита | `curl -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=day"` |

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

## Пробы

| Задача | Команда |
|--------|---------|
| Liveness | `curl "${NODE_NEXUS_URL}/health"` |
| Readiness | `curl "${NODE_NEXUS_URL}/ready"` |
| Метрики | `curl "${NODE_NEXUS_URL}/metrics"` |

Полный каталог endpoint'ов: [HTTP API](api.md). Схемы запросов и ответов:
[интерактивная документация](openapi.html).
