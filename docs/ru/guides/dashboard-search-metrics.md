---
title: Дашборд, поиск и метрики
status: stable
translation_key: guides.dashboard-search-metrics
source_revision: "2026-09-02"
---

# Дашборд, поиск и метрики

Stage E добавляет агрегированные представления, глобальный поиск,
статистику выполнения и поток событий.

> **Дашборд удалён в 2.0:** `GET /api/v2/dashboard/` и `GET /api/v2/dashboard/metrics` удалены. Используйте унифицированные эндпоинты статистики (`GET /.../stats`), описанные ниже — снапшот `ExecutionStatsResponse` без `group_by`, бакеты при `group_by=hour|day|week|month`.

## Унифицированная статистика (замена дашборда)

Вся статистика теперь под сущностью (унифицированный `ExecutionStatsResponse` vs `MetricsBucket`/`StatsBucket`):

- `GET /api/v2/commands/stats` — агрегат по выполнению команд (опционально `?node_id=<uuid>`) — также `GET /commands/stats?node_id`
- `GET /api/v2/commands/{id}/stats` — статистика по конкретной команде — `GET /commands/{id}/stats`
- `GET /api/v2/scripts/stats` и `GET /api/v2/scripts/{id}/stats` — статистика скриптов
- `GET /api/v2/nodes/stats` и `GET /api/v2/nodes/{id}/stats` — статистика нод — `GET /nodes/stats`, `GET /nodes/{id}/stats`
- `GET /api/v2/audit/stats` — статистика аудита (`?group_by=hour|day|week|month`, `?date_from`/`?date_to`) — `GET /audit/stats?group_by=hour|day|week|month`

Без `group_by` возвращается снапшот `ExecutionStatsResponse`:

```json
{
  "total": 42,
  "successful": 38,
  "failed": 4,
  "cancelled": 0,
  "success_rate": 0.904,
  "avg_duration_ms": 1250.5,
  "min_duration_ms": 80.0,
  "max_duration_ms": 5400.0,
  "last_executed_at": "2026-09-02T10:00:00Z"
}
```

`success_rate` — `0..1` (`0.8 = 80%`, `cancelled` исключён из `total`/`success_rate`). Для скриптов в `total` только терминальные `success|error` (legacy `completed|failed`); `cancelled` отдельно, `pending`/`running` исключены. `date_to` — исключительно (`[date_from, date_to)`), `avg_duration_ms` — `GREATEST(0, finished_at - started_at)` с `FILTER (WHERE finished_at IS NOT NULL)`.

С `group_by` возвращается бакетированный ответ (`{buckets: MetricsBucket[]}` / `StatsBucketsResponse`):

```json
{
  "buckets": [
    {
      "period": "2026-09-02 00:00:00+00:00",
      "total": 42,
      "successful": 38,
      "failed": 4,
      "cancelled": 0,
      "avg_duration_ms": 1250.5
    }
  ]
}
```

Для аудита `GET /audit/stats?group_by=...` бакет — `{bucket, count}`, агрегат — `{total, buckets:[{bucket,count}]}`; с `group_by` может возвращаться `BulkResult` бакетов.

### Примеры

```bash
  # Статистика команды — снапшот
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/stats"

  # Статистика команды — бакеты по дням
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/stats?group_by=day&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"

  # Статистика команд для ноды (снапшот)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=<node-id>"

  # Статистика команд для ноды — бакеты
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=<node-id>&group_by=week"

  # Статистика нод — снапшот vs бакеты
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/nodes/stats?group_by=day"

  # Статистика аудита — снапшот vs бакеты
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=hour&date_from=2026-09-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"
```

`group_by` — обязательно `hour`, `day`, `week` или `month`. `date_from` включительно, `date_to` — исключительно.

## Глобальный поиск

```bash
curl --fail-with-body --get \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'q=deploy' \
  "${NODE_NEXUS_URL}/api/v2/search"
```

Ищет по нодам, командам, скриптам и тегам.

## Статистика выполнения (детали сохранены)

См. унифицированную статистику выше. Каждый `ExecutionStatsResponse` возвращает `total`, `successful`, `failed`, `cancelled`, `success_rate` (`0..1`, `0.8 = 80%`, `cancelled` не в `total`), `avg_duration_ms`, `min_duration_ms`, `max_duration_ms` и `last_executed_at`.
Для скриптов в `total` входят только терминальные `success|error` (legacy `completed|failed`); `cancelled` отдельно, `pending`/`running` исключены. `date_to` — исключительно.

## SSE поток событий

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/events/stream"
```

События: `node.status_changed`, `execution.completed`,
`execution.failed`, `script.scheduled`, `job.progress`.

## Экспорт аудита

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=csv&limit=100"
  # или ?fmt=json
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=json&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"
```

Форматы: `json` (по умолчанию) и `csv`. См. [Журнал аудита](audit-log.md) для cursor-пагинации и `GET /audit/stats`.
