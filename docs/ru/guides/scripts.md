---
title: Скрипты и расписания
status: stable
translation_key: guides.scripts
source_revision: "2026-08-16"
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

## Поиск скриптов

Добавьте параметр `search` для фильтрации по имени или описанию:

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'search=deploy' \
  "${NODE_NEXUS_URL}/api/v1/scripts/"
```

Поиск выполняется по полям `name` и `description` с помощью case-insensitive
сопоставления (ILIKE). Ответ возвращает только те скрипты, у которых имя или
описание содержат подстроку поиска.

## Глобальный список тегов скриптов

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/tags"
```

Возвращает отсортированный список уникальных тегов, используемых во всех
скриптах. Подходит для построения автокомплита и фильтров в UI.

## Выполнение по тегам

Скрипт можно выполнить на нодах, отфильтрованных по тегам, вместо перечисления
ID. Параметры `node_ids` и `node_tags` можно комбинировать — результат будет
пересечением (AND).

### Выполнение по ID (как раньше)

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id-1>", "<node-id-2>"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script_id>/execute"
```

### Выполнение по тегам

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_tags": ["web", "production"], "params": {"branch": "main"}}' \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script_id>/execute"
```

Выполнится на всех нодах, имеющих оба тега `web` И `production`.

### Смешанный режим

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["<node-id>"], "node_tags": ["web"], "params": {}}' \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script_id>/execute"
```

Результат — пересечение: ноды из `node_ids`, которые также имеют все указанные
теги. Хотя бы один из параметров `node_ids` или `node_tags` обязателен.

### Ответ

```json
{
  "script_id": "...",
  "total_nodes": 3,
  "results": [
    {"node_id": "...", "node_name": "web-1", "exit_code": 0, "stdout": "...", "stderr": ""},
    {"node_id": "...", "node_name": "web-2", "exit_code": 0, "stdout": "...", "stderr": ""}
  ]
}
```

Поля `exit_code`, `stdout`, `stderr` присутствуют для каждого шага, но на уровне
пакетного ответа `results` содержит агрегированные данные по нодам.

## Повтор выполнения

Повторный запуск завершившейся ошибкой команды или скрипта с теми же параметрами.

### Повтор команды

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/${NODE_ID}/commands/${EXECUTION_ID}/retry"
```

### Повтор скрипта

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/executions/${EXECUTION_ID}/retry"
```

Возвращает новое выполнение с теми же `script_id`, `node_id` и `params`.

## Отмена выполнения

Отмена ещё выполняющегося скрипта:

```bash
curl --fail-with-body -X POST \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/executions/${EXECUTION_ID}/cancel"
```

Отменить можно только выполняющиеся executions. Уже завершённые или упавшие
вернут ошибку.

## История расписаний

Просмотр истории выполнений конкретного расписания (cron-запуски):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/${SCRIPT_ID}/schedule/history?page=1&size=20"
```

Необязательный параметр: `trigger` — фильтр по типу триггера (`manual`,
`scheduled`, `api`). Возвращает пагинированный список выполнений скриптов с
полями `trigger` и `schedule_id`. Включены только executions, созданные через
`execute` или планировщик (выполнения команд не попадают).
