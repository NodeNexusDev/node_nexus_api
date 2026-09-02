---
title: Управление удалённым Docker
status: stable
translation_key: guides.docker
source_revision: "2026-09-02"
---

# Управление удалённым Docker

Docker-операции выполняются через SSH-подключение ноды и требуют доступный
Docker daemon на целевом хосте. Сначала проверьте ноду и получите список
контейнеров. Bulk-вызовы возвращают `BulkResult` (`{total,succeeded,failed,results}`) с `200` при полном успехе или `207 Multi-Status` при частичном; частичная ошибка не
откатывает успешные удалённые операции.

## Контейнеры

Список запущенных контейнеров (cursor-пагинация):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="
  # -> {items,next_cursor,has_more,limit}
```

Список всех контейнеров включая остановленные:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers?all=true&limit=20"
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
`/restart`, `/pause`, `/unpause`, `/rename`, `/logs`, `/stats`, `/top` и `/exec`,
плюс новые одиночные эндпоинты `/kill`, `/update`, `/archive`, `/port`, `/wait`.
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

### Новые одиночные операции (9 операций добавлено в 2.0)

| Путь | Метод | Описание |
|------|-------|----------|
| `/containers/{id}/kill` | `POST` | Kill с сигналом `{"signal": "SIGTERM"}` → `{status:"killed"}` |
| `/containers/{id}/update` | `POST` | Обновление `{"memory": "512m", "cpus": "1.5", "restart_policy": "always"}` → `{status:"updated"}` |
| `/containers/{id}/archive?path=/etc/hosts` | `GET` | Копировать файл из контейнера (`docker cp`) → `{output, path}` |
| `/containers/{id}/archive?path=/tmp/` | `PUT` | Скопировать данные в контейнер (`?path` query, `?data` в query) → `{status:"copied"}` |
| `/containers/{id}/port` | `GET` | Бинды портов `?private_port=80` → `{output, bindings}` |
| `/containers/{id}/wait` | `POST` | Ожидание выхода `?timeout=60` → `{exit_code}` |
| `/system/version` | `GET` | Версия Docker → `{server_version, api_version, go_version, git_commit, build_time, os, arch}` |
| `/system/prune` | `POST` | Системная очистка `?volumes=true` → `{containers_deleted, images_deleted, space_reclaimed}` |
| `/networks/prune` | `POST` | Очистка неиспользуемых сетей → `{output}` |
| `/images/{id}/history` | `GET` | История образа → `{layers:[{id,created,created_by,size,comment}]}` |
| `/images/push` | `POST` | Push образа `{"image": "repo:tag"}` или `/images/{id}/push` → `{image,output,success}` |

Примеры:

```bash
  # Kill
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"signal": "SIGKILL"}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/kill"

  # Update
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"memory": "512m", "cpus": "1.0"}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/update"

  # Archive get/put
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/etc/hosts"
curl --fail-with-body -X PUT -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/archive?path=/tmp/data&data=hello"

  # Port / Wait
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/port?private_port=80"
curl --fail-with-body -X POST -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/${CONTAINER_ID}/wait?timeout=60"
```

Очистка остановленных контейнеров (по-прежнему `POST /containers/prune`):

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/prune"
```

## Images

Pull, inspect, tag, remove и сборка image (списки теперь с cursor-пагинацией):

```bash
## Список с cursor
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

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

## История (новое)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/history"

## Tag
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/alpine:latest/tag" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"repo": "local/alpine", "tag": "v1.0"}'

## Push (новое)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/images/push" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"image": "local/alpine:v1.0"}'
  # или POST /images/{id}/push

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
принадлежностью контейнеров (список теперь с cursor-пагинацией). Prune — новое:

```bash
## Список сетей
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

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

## Очистка неиспользуемых сетей (новое)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/networks/prune"
```

## Volumes

Получение списка, создание, инспекция и удаление Docker volumes (список теперь с cursor-пагинацией):

```bash
## Список volumes
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/volumes?limit=20&cursor=eyJvZmZzZXQiOjIwfQ=="

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

Запрос информации о Docker daemon, версии и использовании диска; prune теперь покрывает систему:

```bash
## Информация о Docker
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/info"

## Версия (новое)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/version"

## Использование диска
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/df"

## Системная очистка (новое)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/system/prune?volumes=false"
```

## Вертикальные bulk-операции (per-node, без fleet)

Fleet `POST /api/v2/docker/bulk/*` удалён. Используйте вертикальные bulk под `POST /nodes/{id}/docker/...` (все возвращают `BulkResult` с `207` при частичном успехе). Для одиночного кейса — `container_ids=[id]`. Для fleet используйте `POST /commands/executions`.

Сводка vert-bulk: `POST /nodes/{id}/docker/containers/{starts,stops,restarts,removals,pauses,unpauses,kills,updates,executions,inspections,logs,stats}` плюс prune (`/containers/prune`, `/images/prune`, `/volumes/prune`, `/networks/prune`, `/system/prune`) и per-container `kill`/`update`/`archive`/`port`/`wait`, networks/volumes/system (`info`/`df`/`version`/`prune`) и 9 новых операций (см. таблицу выше).

| Bulk-путь (POST) | Тело | Элемент BulkResult |
|------------------|------|--------------------|
| `/containers/starts` | `{"container_ids": ["<id>", ...]}` | `{container_id,status,error}` |
| `/containers/stops` | `{"container_ids": [...]}` query `?timeout=10` | то же |
| `/containers/restarts` | `{"container_ids": [...]}` query `?timeout=10` | то же |
| `/containers/removals` | `{"container_ids": [...]}` query `?force=false` | то же |
| `/containers/pauses` | `{"container_ids": [...]}` | то же |
| `/containers/unpauses` | `{"container_ids": [...]}` | то же |
| `/containers/kills` | `{"container_ids": [...], "signal": "SIGTERM"}` | то же |
| `/containers/updates` | `{"container_ids": [...], "memory": "512m", "cpus": "1.0", "restart_policy": "always"}` | то же |
| `/containers/executions` | `{"container_ids": [...], "command": "id", "timeout": 30}` | `{container_id,status,error,stdout,stderr,exit_code}` |
| `/containers/inspections` | `{"container_ids": [...]}` | `{container_id,status,error,data: DockerContainerInspect}` |
| `/containers/logs` | `{"container_ids": [...], "tail": 100, "since": null}` | `{container_id,status,error,logs}` |
| `/containers/stats` | `{"container_ids": [...]}` | `{container_id,status,error,stats: DockerStats}` |
| `/images/pulls` | `{"images": ["alpine:latest"], "timeout": 300}` | `{image,status,error,output}` |
| `/images/removals` | `{"image_ids": [...]}` | `{image,status,error}` |
| `/networks/removals` | `{"network_ids": [...]}` | `{network_id,status,error}` |
| `/volumes/removals` | `{"volume_names": [...]}` | `{volume_name,status,error}` |
| `/containers/prune` | — (system service) | `DockerPruneResponse` (не BulkResult) |
| `/images/prune` | — | `DockerPruneResponse` |
| `/volumes/prune` | — | `DockerVolumePruneResponse` |
| `/networks/prune` | — | `DockerVolumePruneResponse` |
| `/system/prune` | `?volumes=false` | `DockerPruneResponse` |

Примеры (`207` при частичном):

```bash
  # Vert-bulk restart
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/restarts?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_ids": ["app-ctr", "sidecar"]}'
  # {"total":2,"succeeded":1,"failed":1,"results":[{"container_id":"app-ctr","status":"success"}, ...]}

  # Vert-bulk exec
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_ids": ["app-ctr"], "command": "id", "timeout": 30}'

  # Vert-bulk stats
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/docker/containers/stats" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"container_ids": ["app-ctr"]}'
```

Проверяйте каждый элемент `results` после bulk-вызова; `200` — всё успешно, `207` — `succeeded>0 && failed>0`.

## Валидация и безопасность

Идентификаторы, имена images и тайм-ауты валидируются до построения удалённой
команды. Тем не менее используйте SSH-учётную запись с минимальными правами и
считайте выполнение в контейнере привилегированным доступом. После bulk-вызова
проверяйте каждый элемент `results`.
