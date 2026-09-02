---
title: Скрипты и расписания
status: stable
translation_key: guides.scripts
source_revision: "2026-09-02"
---

# Скрипты и расписания

Скрипт — упорядоченный pipeline из inline-команд и сохранённых шаблонов. Для
каждого шага выбирается поведение `stop` или `continue` при ошибке. Ненулевой
код выхода всегда задаёт итоговый статус `error` для ноды, а `continue` лишь
разрешает выполнять следующие шаги. Выполнение может охватывать несколько нод
и возвращает результат по каждой.

Расписания хранятся в PostgreSQL и восстанавливаются при запуске. `timezone`
задаётся IANA-именем и по умолчанию равна `UTC`; пропущенные запуски
объединяются, для расписания действует `max_instances=1`, а
`misfire_grace_seconds` по умолчанию равен 60. APScheduler служит только
runtime-проекцией. Реплики выбирают одного owner через advisory lock PostgreSQL.

До выполнения проверяются все целевые ноды. Ноды обрабатываются с ограниченной
конкурентностью. История хранит fingerprint вместо rendered command, не
сохраняет параметры и обрезает слишком большой вывод с исходным byte count.

## Создание скриптов (bulk-first)

`POST /api/v2/scripts/` — bulk-first без сегмента `bulk`. Отправьте envelope
`{items: [ScriptCreate, ...]}` (1..20 элементов) и получите `BulkResult` с
`201` при полном успехе или `207 Multi-Status` при частичном. Каждый
`ScriptCreate` содержит `name`, `description`, `steps` (массив `{label, type:"command"|"command_id", command?, command_id?, params?, on_failure:"stop"|"continue"}`) и `tags`. Одиночное создание — `items` с одним элементом.

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/scripts/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {
        "name": "deploy",
        "description": "Deploy main branch",
        "tags": ["deploy"],
        "steps": [
          {"label": "pull", "type": "command", "command": "git pull", "params": {}, "on_failure": "stop"},
          {"label": "restart", "type": "command_id", "command_id": "<command-uuid>", "params": {"branch": "main"}, "on_failure": "stop"}
        ]
      }
    ]
  }'
  # -> 201|207 {total,succeeded,failed,results:[{id?,name,status:"success"|"error",error}]}
```

`201` при `failed==0`, `207` при `succeeded>0 && failed>0`. Проверяйте `results[]`.

## Список скриптов (cursor-пагинация)

Только cursor-пагинация. Используйте `cursor` + `limit` → `{items,next_cursor,has_more,limit}`. Поддерживаются `?tag=` (один тег) и `?search=` (ILIKE по `name`/`description`).

```bash
  # Первая страница
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/?limit=20"

  # Следующая страница
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"

  # Фильтр по тегу и поиску
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'tag=deploy' \
  --data-urlencode 'search=deploy' \
  "${NODE_NEXUS_URL}/api/v2/scripts/?limit=20&tag=deploy&search=deploy"
  # -> {items:[{id,name,description,steps,tags,created_at,updated_at}], next_cursor, has_more, limit}
```

Cursor кодирует `{"offset": N}` как base64url JSON; неверный cursor → `422`. Итерируйтесь пока `has_more == true`. `search` ищет по `name` и `description` (ILIKE).

## Глобальный список тегов скриптов

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/tags"
```

Возвращает отсортированный список уникальных тегов, используемых во всех
скриптах. Подходит для построения автокомплита и фильтров в UI.

## Выполнение скриптов

### Одиночное выполнение (per script)

Скрипт можно выполнять на нодах, отфильтрованных по ID и/или тегам (пересечение AND). Требуется хотя бы один из `node_ids` или `node_tags`.

```bash
  # По ID
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id-1>", "<node-id-2>"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script_id>/execute"

  # По тегам (все ноды с обоими тегами)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_tags": ["web", "production"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script_id>/execute"

  # Смешанный (пересечение: ноды из node_ids, имеющие также теги)
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id>"], "node_tags": ["web"], "params": {}}' \
  "${NODE_NEXUS_URL}/api/v2/scripts/<script_id>/execute"
  # -> {script_id, total_nodes, results:[{node_id, node_name, exit_code, stdout, stderr}]}
```

Поля `exit_code`, `stdout`, `stderr` внутри `steps` возвращаются в `GET /scripts/{id}/executions`; ответ `execute` агрегирует по нодам.

### Bulk-выполнения M×N (рекомендуется)

Выполните несколько скриптов на нескольких нодах за один вызов (`M×N ≤100`) с обработкой `207`.

```bash
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "script_ids": ["<script-1>", "<script-2>"],
    "node_ids": ["<node-1>", "<node-2>"],
    "node_tags": [],
    "params": {
      "<script-1>": {"branch": "main"},
      "<script-2>": {}
    }
  }'
  # -> {batch_id, total, succeeded, failed, results:[{script_id,execution_id,node_id,node_name,status:"success"|"error",steps:[{step_index,label,command_fingerprint,stdout,stderr,stdout_bytes,stderr_bytes,truncated,exit_code}],error}]}
  # 200 всё успешно, 207 частично

  # С фильтрацией по тегам
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{
    "script_ids": ["<script-1>"],
    "node_ids": [],
    "node_tags": ["production"],
    "params": {}
  }'
```

Ограничение `M×N`: `len(script_ids) * max(len(node_ids), len(node_tags) or 1) ≤100`, иначе `422`. Проверяйте `results[]` по `status`; частичные ошибки не откатывают успешные выполнения.

История выполнений скрипта (cursor-пагинация):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/executions?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # -> {items:[{id, script_id, node_id, params, status, steps:[...], started_at, finished_at}], next_cursor, has_more, limit}
```

## Retries и cancels (bulk)

Retries заново выполняют с теми же `script_id`, `node_id` и `params`. Cancels прерывают ещё выполняющиеся executions. Оба — bulk-first с `207` и поддерживают опциональный query `?timeout=` (1..600 секунд, default 30/60) для ограничения ожидания.

```bash
  # Bulk retry (с timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions/retries?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>", "<exec-2>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"retry_scheduled"|"error",message}]}

  # Bulk cancel (с timeout)
curl --fail-with-body -X POST \
  "${NODE_NEXUS_URL}/api/v2/scripts/executions/cancels?timeout=30" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"execution_ids": ["<exec-1>"]}'
  # -> {total,succeeded,failed,results:[{execution_id,status:"cancelled"|"error",message}]}
```

Есть также совместимые одиночные эндпоинты (`POST /scripts/executions/{id}/retry?timeout=30`, `/cancel?timeout=30` и `POST /nodes/{id}/commands/{id}/retry` для команд), но предпочитайте bulk. Отменить можно только `running` executions.

## Статистика

Унифицированные stats без `group_by` возвращают снапшот `ExecutionStatsResponse`; с `group_by` — `{buckets: [{period,total,successful,failed,cancelled,avg_duration_ms}]}`.

```bash
  # Снапшот — все скрипты
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/stats"
  # -> {total, successful, failed, cancelled, avg_duration_ms}

  # Снапшот с фильтром по ноде и датам
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/stats?node_id=${NODE_ID}&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"

  # Бакеты (группировка)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/stats?node_id=${NODE_ID}&group_by=day"
  # -> {buckets:[{period,total,successful,failed,cancelled,avg_duration_ms}]}

  # По конкретному скрипту — снапшот и бакеты
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/stats"

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/stats?group_by=hour&date_from=2026-09-01T00:00:00Z"
  # -> {buckets:[...]} если указан group_by
```

`group_by` принимает `hour|day|week|month`; `date_from`/`date_to` — ISO 8601 UTC.

## История расписаний

Просмотр истории выполнений конкретного расписания (cron-запуски):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/scripts/${SCRIPT_ID}/schedule/history?cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
  # cursor-пагинация (CursorPage[ScriptExecutionResponse])
```

Необязательный параметр: `trigger` — фильтр по типу триггера (`manual`,
`scheduled`, `api`). Возвращает cursor-пагинированный список выполнений скриптов с
полями `trigger` и `schedule_id`. Включены только executions, созданные через
`execute` или планировщик (выполнения команд не попадают). Legacy `?page`/`size` alias больше не каноничен — используйте `cursor`/`limit`.
