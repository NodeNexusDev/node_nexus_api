---
title: Журнал аудита
status: stable
translation_key: guides.audit-log
source_revision: "2026-09-02"
---

# Журнал аудита

Журнал аудита фиксирует значимые для безопасности действия и изменения
состояния. Запись содержит действие, время, необязательный идентификатор ноды,
идентификатор субъекта и подробности. Используйте журнал как источник
операционных данных, но не как замену внешнему неизменяемому хранилищу событий.

## Поиск событий (cursor-пагинация)

Просматривать события может любой действительный ключ. Фильтры принимают ноду,
действие или оба значения. Пагинация — **cursor** (`GET /audit/?cursor=&limit=2 → {items,next_cursor,has_more}`), а не `page`/`size`/`total`. Итерируйтесь по `has_more` + `next_cursor` — т.е. `{items, next_cursor, has_more, limit}` вместо `page`/`size`/`total`.

```bash
curl --get --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode "node_id=${NODE_ID}" \
  --data-urlencode 'action=execute_failed' \
  --data-urlencode 'cursor=eyJvZmZzZXQiOjIwfQ==' \
  --data-urlencode 'limit=2' \
  "${NODE_NEXUS_URL}/api/v2/audit/"
  # cursor=eyJvZmZzZXQiOjIwfQ== == {"offset":20} base64url
```

Ответ:

```json
{
  "items": [
    {"id": "...", "node_id": "...", "action": "execute_failed", "user": "admin", "details": "...", "created_at": "2026-09-02T10:00:00Z"}
  ],
  "next_cursor": "eyJvZmZzZXQiOjIyfQ==",
  "has_more": true,
  "limit": 2
}
```

Основные действия: `create`, `update`, `delete`, `check`, `execute` и
`execute_failed`. На последней странице `next_cursor` равен `null`, `has_more` — `false`. Невалидный курсор — `422`.

Итерация:

```bash
  # страница 1
curl --get --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?limit=50"
  # -> {items,next_cursor,has_more}
  # страница 2
curl --get --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/?cursor=<next_cursor>&limit=50"
```

### Фильтрация по пользователю и дате

Дополнительные параметры запроса позволяют фильтровать по пользователю и
диапазону дат (совмещаются с `cursor`/`limit`/`node_id`/`action`):

```bash
curl --get --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  --data-urlencode 'user=admin' \
  --data-urlencode 'date_from=2026-08-01T00:00:00' \
  --data-urlencode 'date_to=2026-08-16T23:59:59' \
  --data-urlencode 'limit=20' \
  "${NODE_NEXUS_URL}/api/v2/audit/"
```

Параметры:

| Параметр | Описание | Пример |
|----------|----------|--------|
| `user` | Фильтр по идентификатору субъекта | `user=admin` |
| `date_from` | Начало диапазона (ISO 8601) | `date_from=2026-08-01T00:00:00` |
| `date_to` | Конец диапазона (ISO 8601) | `date_to=2026-08-31T23:59:59` |
| `cursor` | Непрозрачный курсор (base64url JSON offset) | `cursor=eyJvZmZzZXQiOjIwfQ==` |
| `limit` | Размер страницы 1..100 (по умолчанию 20) | `limit=20` |

Фильтры можно комбинировать с `node_id` и `action`. Устаревшие `page`/`size`/`total` больше не возвращаются — используйте `has_more`/`next_cursor`.

## Статистика

Агрегированная статистика аудита — `GET /audit/stats?group_by=hour|day|week|month` (снапшот `ExecutionStatsResponse` vs `MetricsBucket`, для аудита `{bucket,count}`):

```bash
  # Явная ссылка на эндпоинт
  # GET /audit/stats
  # GET /audit/stats?group_by=hour|day|week|month
```

Примеры:

```bash
  # Снапшот (агрегат)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats"
  # -> {"total": 123, "buckets": []}

  # Бакеты
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=day&date_from=2026-08-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"
  # -> {"total": 123, "buckets": [{"bucket": "2026-09-01", "count": 42}, ...]}
  # или BulkResult бакетов при group_by: {"total":..., "succeeded":..., "failed":0, "results": [{"bucket","count"}]}

  # Поддерживаемые group_by
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=hour"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=week"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=month"
```

`group_by` — обязательно `hour`, `day`, `week` или `month`. `date_from` включительно, `date_to` — исключительно.

## Экспорт (CSV/JSON)

Экспортируйте события аудита для внешнего анализа в формате JSON или CSV с cursor-пагинацией:

```bash
  # CSV (по умолчанию)
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=csv&limit=100"

  # JSON с cursor
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/exports?fmt=json&cursor=eyJvZmZzZXQiOjIwfQ==&limit=20"

  # Устаревший алиас /audit/export?fmt=csv — используйте /audit/exports
```

Поддерживаемые форматы: `json` и `csv` (по умолчанию `csv`). `limit` 1..100 (по умолчанию 20), опционально `cursor` (base64url offset). Фильтры `from_date`/`to_date`/`action`/`node_id` применимы.

См. [Дашборд, поиск и метрики](dashboard-search-metrics.md) для live SSE-потока
и унифицированной статистики выполнения (`ExecutionStatsResponse` vs `StatsBucket`/`MetricsBucket`).

## Срок хранения и удаление

При запуске приложение удаляет записи старше значения
`AUDIT_LOG_RETENTION_DAYS`. Значение `0` отключает автоматическую очистку; в
этом случае при необходимости настройте внешний процесс хранения.

Полное удаление журнала доступно только по мастер-ключу и требует явного
подтверждения:

```bash
curl --fail-with-body -X DELETE \
  -H "X-API-Key: ${MASTER_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/?confirm=yes"
```

Операцию нельзя отменить средствами приложения. Сначала экспортируйте или
сохраните необходимые данные и зафиксируйте причину удаления вне очищаемого
журнала.
