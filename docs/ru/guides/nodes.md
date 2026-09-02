---
title: Управление нодами
status: stable
translation_key: guides.nodes
source_revision: "2026-09-02"
---

# Управление нодами

Ноды — это удалённые серверы, доступные по SSH. Каждая нода хранит
зашифрованные учётные данные, метаданные подключения, теги, поле `description`
и статус последней проверки.

> **Заметки удалены в 2.0:** таблица `notes` и эндпоинты `/api/v2/notes/*` удалены — поле description заменяет notes (description field replaces notes). Используйте поле `description` самой ноды (`PATCH /api/v2/nodes/{id} {"description": "..."}`) — `GET /api/v2/nodes/{id}` теперь возвращает `description`. У `commands`/`scripts` поле `description` уже существовало.

## Создание нод (bulk)

Bulk-first без сегмента `bulk`. `POST /api/v2/nodes/` принимает конверт
`{items: [NodeCreate, ...]}` (1..20 элементов) и возвращает `BulkResult` с кодами `201` при полном успехе или `207 Multi-Status` при частичном (201|207 BulkResult). Полный провал — `200` по контракту bulk-конверта. Пример: `POST /api/v2/nodes/` с `{items:[{name,host,port,connection_type,tags,description,has_docker,docker_host}]}` → 201|207.

Поля элемента: `name`, `host`, `port` (1..65535, по умолчанию 22), `connection_type` (`ssh`), `username`, `password` / `ssh_key` + опционально `passphrase`, `tags` (массив), `description` (до 1000 символов, nullable), `has_docker` (bool), `docker_host` (требует `has_docker=true`, валидируется).

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "name": "web-01",
        "host": "192.0.2.10",
        "port": 22,
        "connection_type": "ssh",
        "username": "ops",
        "password": "change-me",
        "tags": ["production", "frontend"],
        "description": "Основной фронтенд",
        "has_docker": true,
        "docker_host": "unix:///var/run/docker.sock"
      }
    ]
  }'
```

Ответ `201` (всё успешно) или `207` (частично):

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "results": [
    {"node_id": "550e8400-e29b-41d4-a716-446655440000", "status": "success", "error": ""}
  ]
}
```

При частичном успехе конверт содержит `status: "success" | "error"` и текст `error` по каждому элементу; успешные создания сохраняются, неуспешные не откатывают уже созданные. Форма `BulkResult`: `{total,succeeded,failed,results:[{id,status,error,output?}]}`.

Сохраните возвращённые `node_id` для метрик, выполнения команд и проверок.

### Аутентификация по SSH-ключу

Вместо пароля передайте содержимое приватного ключа в поле `ssh_key`. Если
ключ зашифрован, укажите passphrase:

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [{
      "name": "web-02",
      "host": "192.0.2.11",
      "port": 22,
      "connection_type": "ssh",
      "username": "ops",
      "ssh_key": "<содержимое-приватного-ключа>",
      "passphrase": "passphrase-ключа",
      "tags": [],
      "description": "Нода с SSH-ключом"
    }]
  }'
```

`passphrase` — необязательное поле, требуется только для зашифрованных
приватных ключей. Поля `password`, `ssh_key` и `passphrase` шифруются
при сохранении и никогда не возвращаются в ответах API (`GET /nodes/{id}` отдаёт `description`, `has_docker`, `docker_host`, но не секреты).

## Валидация учётных данных

Проверьте SSH-подключение по предоставленным учётным данным без сохранения
ноды в базу данных. Полезно перед созданием ноды для проверки доступности.

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/nodes/validate-credentials" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "host": "192.0.2.10",
    "port": 22,
    "username": "ops",
    "password": "change-me"
  }'
```

Валидация также работает с SSH-ключом — замените `password` на `ssh_key`
(и опционально `passphrase`):

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

## Список и фильтрация (cursor-пагинация)

Только cursor-пагинация. Поля `total`/`page`/`size` удалены (дорогой `COUNT(*)`).
Используйте `limit` + непрозрачный `cursor` → `{items, next_cursor, has_more, limit}`.

```bash
  # Первая страница
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?limit=20"

  # Следующая страница — cursor из предыдущего ответа
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # cursor=eyJvZmZzZXQiOjIwfQ== декодируется как {"offset":20} (base64url JSON)
```

Форма ответа:

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "web-01",
      "host": "192.0.2.10",
      "port": 22,
      "connection_type": "ssh",
      "status": "active",
      "username": "ops",
      "docker_host": null,
      "has_docker": false,
      "tags": ["production"],
      "description": "Основной фронтенд",
      "created_at": "2026-09-02T10:00:00Z",
      "updated_at": "2026-09-02T10:00:00Z"
    }
  ],
  "next_cursor": "eyJ0cyI6IjIwMjYtMDktMDJUMTA6MDA6MDBaIiwiaWQiOiI1NTBlODQwMC1lMjliLTQxZDQtYTcxNi00NDY2NTU0NDAwMDAifQ==",
  "has_more": true,
  "limit": 20
}
```

Итерируйтесь, пока `has_more` true, передавая `next_cursor` как `cursor`. На последней странице `next_cursor` равен `null`. Невалидный курсор — `422`.

Фильтрация по тегам с логикой AND:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tags=production' \
  --data-urlencode 'tags=frontend' \
  "${NODE_NEXUS_URL}/api/v2/nodes/?limit=20"
```

Поиск по имени/хосту:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?search=web&limit=20"
```

Параметры `page`/`size` больше не поддерживаются на этом эндпоинте — используйте `cursor`/`limit`.

## Одиночный CRUD

```bash
  # Получить
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"

  # Обновить (частично) — description заменяет notes
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"description": "Обновлённая документация", "tags": ["production"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"

  # Удалить
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}"
  # 204 No Content
```

## Проверка подключения (single)

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/check/"
```

Успешная проверка подтверждает доступность по SSH. Статус ноды обновляется
автоматически.

## Системные метрики (single)

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/metrics/"
```

Возвращает информацию о CPU, памяти, дисках и нагрузке с удалённого хоста.

## История команд ноды

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/commands/history?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

Возвращает cursor-пагинированный список выполненных команд на данной ноде (`{items,next_cursor,has_more,limit}`). Каждая
запись содержит fingerprint команды, exit code, обрезанные stdout/stderr с
оригинальными byte count, а также время выполнения. Вывод ограничивается
политикой `bound_output()`.

## История статусов (cursor)

Запросите историю изменений статуса (active/unreachable/error) с cursor-пагинацией (`CursorPage`, курсор кодирует offset):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/${NODE_ID}/status-history?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

Ответ:

```json
{
  "items": [
    {"id": "...", "node_id": "...", "old_status": "unreachable", "new_status": "active", "source": "check", "changed_at": "2026-09-02T10:00:00Z"}
  ],
  "next_cursor": "eyJvZmZzZXQiOjQwfQ==",
  "has_more": false,
  "limit": 20
}
```

Итерируйтесь через `next_cursor`/`has_more`. Невалидный курсор — `422`. На уровне сервиса поддерживаются фильтры `from`/`to` (ISO 8601) и `status`, если доступны.

## Массовые операции (без слова `bulk`)

Все bulk-эндпоинты нод теперь без сегмента `bulk` и возвращают `BulkResult` (`{total,succeeded,failed,results}`) с `200` при полном успехе или `207 Multi-Status` при частичном; `422` когда все неуспешны (где применимо). Результаты — по каждой ноде с `status: "success"|"error"` и не откатывают успешные.

| Действие | Метод и путь | Тело | Коды |
|----------|--------------|------|------|
| Массовое обновление | `PATCH /api/v2/nodes/` | `{"updates": [{"id": "<uuid>", "changes": {"tags": [...], "description": "...", "has_docker": true}}]}` (1..100) | `200` / `207` |
| Массовое удаление | `POST /api/v2/nodes/deletions` | `{"ids": ["<uuid>", ...]}` (1..100) | `200` / `207` |
| Массовая проверка | `POST /api/v2/nodes/checks` | `{"ids": ["<uuid>", ...]}` (1..100) | `200` / `207` |
| Массовые метрики | `POST /api/v2/nodes/metrics` | `{"ids": ["<uuid>", ...]}` (1..100) | `200` / `207` |
| Валидация учётных данных | `POST /api/v2/nodes/credential-validations` | `{"ids": ["<uuid>"], "tags": ["prod"]}` (ids или tags, 1..100) | `200` / `207` |

> Удалены старые пути: `POST /nodes/bulk/check`, `POST /nodes/bulk/tags/add`, `POST /nodes/bulk/tags/remove`, `POST /nodes/bulk/delete` (и `PATCH /nodes/bulk/update`). Массовое добавление/удаление тегов теперь через `PATCH /nodes/` с `changes.tags`. Фильтрация по тегам на уровне fleet осталась только в `POST /nodes/credential-validations`.

### Массовое обновление (PATCH коллекции)

```bash
curl --fail-with-body -X PATCH \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "updates": [
      {"id": "<id-1>", "changes": {"tags": ["production","frontend"], "description": "Обновлено"}},
      {"id": "<id-2>", "changes": {"has_docker": true, "docker_host": "unix:///var/run/docker.sock"}}
    ]
  }' \
  "${NODE_NEXUS_URL}/api/v2/nodes/"
  # 200 или 207
  # {"total":2,"succeeded":2,"failed":0,"results":[{"node_id":"<id-1>","status":"success"}, ...]}
```

### Массовое удаление

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/deletions"
```

### Массовая проверка

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/checks"
```

### Массовые метрики

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>", "<id-2>"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/metrics"
  # results: [{node_id, node_name, status, metrics:{cpu,memory,disk,load_average,uptime_since}, error}]
```

### Валидация учётных данных (bulk)

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"ids": ["<id-1>"], "tags": ["production"]}' \
  "${NODE_NEXUS_URL}/api/v2/nodes/credential-validations"
  # results: [{node_id, node_name, status:"success"|"error", message}]
```

Все bulk-ответы — единый конверт `BulkResult`; проверяйте каждый элемент `results[]` на `status`/`error`. Для одиночной ноды используйте `ids=[id]` через bulk.

Актуальные схемы запросов и ответов смотрите в Swagger UI (`/docs`).
