---
title: Дашборд, поиск и метрики
status: stable
translation_key: guides.dashboard-search-metrics
source_revision: "2026-08-17"
---

# Дашборд, поиск и метрики

Stage E добавляет агрегированные представления, глобальный поиск,
статистику выполнения и поток событий.

## Обзор дашборда

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/dashboard/"
```

Возвращает агрегированные счётчики нод, Docker-контейнеров, скриптов,
команд и последней активности аудита.

## Метрики дашборда (временные ряды)

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/dashboard/metrics?group_by=day"
```

Параметры:

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `group_by` | `day` | Гранулярность: `hour`, `day`, `week`, `month` |
| `date_from` | — | Начало диапазона (ISO 8601) |
| `date_to` | — | Конец диапазона (ISO 8601) |

Ответ содержит массивы `command_metrics` и `script_metrics`. Каждый бакет
содержит `period`, `total`, `successful`, `failed`, `cancelled` и `avg_duration_ms`.
`date_from` включительно, `date_to` — исключительно (`[date_from, date_to)`).
`avg_duration_ms` — `GREATEST(0, finished_at - started_at)` с `FILTER (WHERE finished_at IS NOT NULL)`.

## Глобальный поиск

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'q=deploy' \
  "${NODE_NEXUS_URL}/api/v1/search"
```

Ищет по нодам, командам, скриптам и тегам.

## Статистика выполнения

### Статистика команд

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/commands/<command-id>/stats"
```

### Статистика скриптов

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/scripts/<script-id>/stats"
```

### Статистика команд для ноды

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/commands/stats?node_id=<node-id>"
```

Каждый эндпоинт возвращает `total`, `successful`, `failed`, `cancelled`, `success_rate` (`0..1`, `0.8 = 80%`, `cancelled` не в `total`), `avg_duration_ms`, `min_duration_ms`, `max_duration_ms` и `last_executed_at`.
Для скриптов в `total` входят только терминальные `success|error` (legacy `completed|failed`); `cancelled` отдельно, `pending`/`running` исключены. `date_to` — исключительно.

## SSE поток событий

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/events/stream"
```

События: `node.status_changed`, `execution.completed`,
`execution.failed`, `script.scheduled`, `job.progress`.

## Экспорт аудита

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/audit/export?fmt=csv"
```

Форматы: `json` (по умолчанию) и `csv`.
