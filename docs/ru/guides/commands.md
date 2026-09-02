---
title: Переиспользуемые команды
status: stable
translation_key: guides.commands
source_revision: "2026-09-02"
---

# Переиспользуемые команды

Шаблоны команд задают именованные параметры и поддерживают теги. Создайте
шаблон, выполните его на ноде со значениями параметров и проверьте exit code,
stdout и stderr. Параметры валидируются до удалённого выполнения; не собирайте
недоверенные shell-фрагменты за пределами модели шаблонов.

## Создание команд (bulk-first)

`POST /api/v2/commands/` — bulk-first без сегмента `bulk`. Отправьте envelope
`{items: [CommandCreate, ...]}` (1..20 элементов) и получите `BulkResult` с
`201` при полном успехе или `207 Multi-Status` при частичном. Каждый
`CommandCreate` содержит `name`, `command` (с плейсхолдерами `{{ param }}`),
`parameters` (`{name, type:"string"|"integer"|"boolean", required, default, description}`),
`tags` и `description`. Одиночное создание — `items` с одним элементом.

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/commands/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "name": "disk-usage",
        "command": "df -h {{ mount }}",
        "parameters": [{
          "name": "mount",
          "type": "string",
          "required": true,
          "description": "Absolute mount path"
        }],
        "tags": ["diagnostics"],
        "description": "Show disk usage"
      },
      {
        "name": "uptime",
        "command": "uptime",
        "parameters": [],
        "tags": ["diagnostics"]
      }
    ]
  }'
  # -> 201|207 {total,succeeded,failed,results:[{id?,name,status:"success"|"error",error}]}
```

`201` при `failed==0`, `207` при `succeeded>0 && failed>0`. Проверяйте каждый
элемент `results[]`; успешные шаблоны сохраняются, неуспешные — нет.

Старый одиночный `POST /commands` без `items` больше не поддерживается — оберните шаблон в `items`.

## Список команд (cursor-пагинация)

Только cursor-пагинация (`COUNT(*)` убран). Используйте `cursor` + `limit` → `{items,next_cursor,has_more,limit}`. Поддерживаются `?tag=` (один тег) и `?search=` (ILIKE по `name`/`description`).

```bash
  # Первая страница
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/?limit=20"

  # Следующая страница
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"

  # Фильтр по тегу и поиску
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tag=diagnostics' \
  --data-urlencode 'search=disk' \
  "${NODE_NEXUS_URL}/api/v2/commands/?limit=20"
  # -> {items:[{id,name,command,parameters,tags,description,created_at,updated_at}], next_cursor, has_more, limit}
```

Cursor кодирует `{"offset": N}` как base64url JSON; неверный cursor → `422`. Итерируйтесь пока `has_more == true`.

## Выполнение шаблонов

### Одиночное выполнение (legacy)

Сохраните UUID из ответа bulk-создания и выполните на одной ноде:

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/execute" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d "{\"node_id\": \"${NODE_ID}\", \"params\": {\"mount\": \"/\"}}"
```

Код `exit_code: 0` означает успех. Сохраняйте `stderr`: туда могут идти
предупреждения. Поддерживаются `string`, `integer` и `boolean`; отсутствие
обязательного значения — ошибка до SSH.

### Bulk-выполнения M×N (рекомендуется)

Выполните несколько команд на нескольких нодах за один вызов (`M×N ≤100`). `207` при частичных ошибках.

```bash
  # M команд × N нод — параметры по ключу-строке command_id
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "command_ids": ["<cmd-1>", "<cmd-2>"],
    "node_ids": ["<node-1>", "<node-2>"],
    "node_tags": [],
    "params": {
      "<cmd-1>": {"mount": "/"},
      "<cmd-2>": {}
    }
  }'
  # -> {batch_id, total, succeeded, failed, results:[{command_id,command,node_id,node_name,stdout,stderr,exit_code,status:"success"|"error",error}]}
  # 200 всё успешно, 207 частично

  # С фильтрацией по тегам (ноды = пересечение node_ids ∩ node_tags; хотя бы один источник)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "command_ids": ["<cmd-1>"],
    "node_ids": [],
    "node_tags": ["production"],
    "params": {}
  }'
```

Ограничение `M×N`: `len(command_ids) * max(len(node_ids), len(node_tags) or 1) ≤100`, иначе `422`.

### Raw-выполнения M×N

Выполнение произвольных строк без шаблона (для ad-hoc операций):

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/raw-executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "commands": ["df -h /", "uptime"],
    "node_ids": ["<node-1>"],
    "node_tags": []
  }'
  # -> {batch_id, total, succeeded, failed, results:[{command,node_id,node_name,stdout,stderr,exit_code,status,error}]}
```

То же ограничение `M×N ≤100` и обработка `207`.

## Retries и cancels (bulk)

Retries заново рендерит шаблон и выполняет с теми же нодами/параметрами. Cancel прерывает ещё выполняющиеся executions. Оба — bulk-first (`207`) и поддерживают опциональный query `?timeout=` (1..600 секунд, default 30/60) для ограничения ожидания.

```bash
  # Retry нескольких выполнений команд (с timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions/retries?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>", "<exec-2>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"retry_scheduled"|"error",message}]}

  # Отмена нескольких выполнений (с timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/commands/executions/cancels?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"cancelled"|"error",message}]}
```

Остаётся алиас для одиночного retry (`POST /nodes/{id}/commands/{execution_id}/retry?timeout=30`); предпочитайте bulk-эндпоинты. Отменить можно только `running` executions.

История по bulk-batch:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/executions/history?batch_id=${BATCH_ID}&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # -> {items, next_cursor, has_more, limit} (CursorPage[CommandHistoryResponse])
```

История по ноде:

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/history?node_id=${NODE_ID}&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

## Статистика

Унифицированные stats заменили старые dashboard-метрики. Без `group_by` ответ — снапшот `ExecutionStatsResponse`; с `group_by` — `{buckets: [{period,total,successful,failed,cancelled,avg_duration_ms}]}`.

```bash
  # Снапшот — все команды
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats"
  # -> {total, successful, failed, cancelled, avg_duration_ms}

  # Снапшот с фильтром по ноде и диапазону дат
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=${NODE_ID}&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"

  # Бакеты (группировка)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=${NODE_ID}&group_by=day"
  # -> {buckets:[{period,total,successful,failed,cancelled,avg_duration_ms}]}

  # По конкретной команде — снапшот и бакеты
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/stats"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/${COMMAND_ID}/stats?group_by=hour&date_from=2026-09-01T00:00:00Z"
  # -> {buckets:[...]} если указан group_by
```

`group_by` принимает `hour|day|week|month`; `date_from`/`date_to` — ISO 8601 UTC.

## Поиск команд

Добавьте параметр `search` для фильтрации по имени или описанию:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'search=disk' \
  "${NODE_NEXUS_URL}/api/v2/commands/"
```

Поиск выполняется по полям `name` и `description` с помощью case-insensitive
сопоставления (ILIKE). Ответ возвращает только те шаблоны, у которых имя или
описание содержат подстроку поиска.

## Глобальный список тегов команд

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/tags"
```

Возвращает отсортированный список уникальных тегов, используемых во всех
шаблонах команд. Подходит для построения автокомплита и фильтров в UI.
