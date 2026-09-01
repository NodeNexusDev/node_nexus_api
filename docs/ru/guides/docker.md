---
title: Управление удалённым Docker
status: stable
translation_key: guides.docker
source_revision: "2026-08-25"
---

# Управление удалённым Docker

Docker-операции выполняются через SSH-подключение ноды и требуют доступный
Docker daemon на целевом хосте. Сначала проверьте ноду и получите список
контейнеров. Bulk-вызовы возвращают отдельные результаты; частичная ошибка не
откатывает успешные удалённые операции.

## Контейнеры

Список запущенных контейнеров:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers"
```

Список всех контейнеров включая остановленные:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?all=true"
```

Создание контейнера из image. Строка `command` разбивается на отдельные
аргументы перед отправкой в Docker:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "image": "alpine:latest",
    "name": "my-ctr",
    "command": "sleep 60",
    "ports": {"80/tcp": "8080"},
    "volumes": {"/host": {"bind": "/container", "mode": "rw"}},
    "env": ["ENV_VAR=value"],
    "labels": {"com.example.foo": "bar"},
    "network": "bridge",
    "restart_policy": "always"
  }'
```

Инспекция контейнера:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"
```

Используйте возвращённый ID или имя контейнера в путях `/start`, `/stop`,
`/restart`, `/pause`, `/unpause`, `/rename`, `/logs`, `/stats`, `/top` и `/exec`.
Для изменения состояния нужен ключ `read-write`:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/exec" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"command": "id", "timeout": 30}'
```

Удаление контейнера:

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}"
```

Получение логов контейнера:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/logs?tail=100"
```

Получение статистики ресурсов контейнера:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/stats"
```

Очистка остановленных контейнеров:

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"
```

## Images

Pull, inspect, tag, remove и сборка image:

```bash
## Pull
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/pull" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"image": "alpine:latest", "timeout": 120}'

## Inspect
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest"

## Tag
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/tag" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"repo": "local/alpine", "tag": "v1.0"}'

## Сборка из Dockerfile, переданного через stdin
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/build" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "dockerfile": "FROM alpine:latest\nRUN echo hello > /marker",
    "tag": "local/built:v1",
    "build_args": {"VERSION": "1.0"},
    "no_cache": true
  }'

## Remove
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/local/alpine:v1.0"

## Очистка неиспользуемых images
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/prune"
```

## Сети

Получение списка, создание, инспекция, удаление Docker-сетей и управление
принадлежностью контейнеров:

```bash
## Список сетей
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks"

## Создание bridge-сети
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"name": "my-network", "driver": "bridge"}'

## Инспекция сети
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"

## Подключение контейнера к сети
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/connect" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_id": "${CONTAINER_ID}"}'

## Отключение контейнера от сети
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}/disconnect" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_id": "${CONTAINER_ID}"}'

## Удаление сети
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/${NETWORK_ID}"
```

## Volumes

Получение списка, создание, инспекция и удаление Docker volumes:

```bash
## Список volumes
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes"

## Создание именованного volume
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"name": "my-vol", "driver": "local"}'

## Инспекция volume
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"

## Удаление volume
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/${VOLUME_NAME}"

## Очистка неиспользуемых volumes
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes/prune"
```

## Система

Запрос информации о Docker daemon и использовании диска:

```bash
## Информация о Docker
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/info"

## Использование диска
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/df"
```

## Bulk-операции

Bulk endpoints под `/api/v2/docker/bulk/` работают с несколькими нодами. Можно
передать явные `node_ids`, `node_tags` или оба варианта. Теги разрешаются в
Docker-ноды и объединяются с явными ID. Результаты возвращаются по нодам;
частичная ошибка не откатывает успешные удалённые операции.

Доступные bulk-действия: `start`, `stop`, `restart`, `exec`, `inspect`, `logs`,
`stats`.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/docker/bulk/restart" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "node_ids": [],
    "node_tags": ["prod"],
    "container_id": "app-ctr",
    "timeout": 30
  }'
```

Требуется хотя бы одно из полей `node_ids` или `node_tags`. Для `bulk/exec`
также обязательно поле `command`.

## Валидация и безопасность

Идентификаторы, имена images и тайм-ауты валидируются до построения удалённой
команды. Тем не менее используйте SSH-учётную запись с минимальными правами и
считайте выполнение в контейнере привилегированным доступом. После bulk-вызова
проверяйте каждый элемент `results`.
