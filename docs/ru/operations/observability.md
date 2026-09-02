---
title: Наблюдаемость
status: stable
translation_key: operations.observability
source_revision: "2026-09-02"
---

# Наблюдаемость

Prometheus metrics доступны по `PROMETHEUS_PATH`, если включены. OpenTelemetry
отправляет traces в `OTEL_ENDPOINT`. Структурированные логи содержат request и
lifecycle events. Настройте alerts на readiness, долю ошибок и timeout, latency,
ошибки БД и scheduler. Не собирайте API keys, SSH credentials и private keys.

## Корреляция запросов

Каждый запрос получает заголовок `X-Request-ID` в ответе. Вы можете передать
свой `X-Request-ID`, и API вернёт его обратно. Ошибочные ответы для validation
failures, HTTP exceptions и domain errors содержат тот же id в JSON теле как
`request_id` (`string|null`), что позволяет связывать клиентские ошибки с
серверными логами.

## Метрики

Прикладные метрики используют префикс `node_nexus_`. HTTP-метрики также
экспортируются стандартным Prometheus FastAPI instrumentor'ом с лейблами
`method` и `handler`. Метрики audit outbox показывают успешные доставки, ошибки,
повторные попытки, количество ожидающих событий и возраст самого старого
события. Метрики scheduler отражают ownership, готовность восстановления,
ошибки регистрации, результаты и длительность выполнений. Дополнительно
доступны количество активных персистентных расписаний, misfire, пропуски из-за
overlap и задержка относительно планового времени запуска.

Настройте alerts на рост `node_nexus_audit_pending`, увеличение возраста
старейшего события, ошибки регистрации расписаний и нулевую готовность
scheduler. Значение `node_nexus_scheduler_owner 0` у non-owner реплики само по
себе не является ошибкой, если advisory lock удерживает другая исправная
реплика.

Prometheus в 2.0 без изменений: `PROMETHEUS_ENABLED=true` публикует метрики на
`PROMETHEUS_PATH` (по умолчанию `/metrics`), instrumentor исключает `/health`,
`/ready` и сам путь метрик.

## Унифицированная статистика (замена Dashboard)

> **Удалено в 2.0:** `GET /api/v2/dashboard/` и `GET /api/v2/dashboard/metrics`
> удалены. Используйте унифицированные эндпоинты статистики, описанные ниже.
> Агрегация Docker через `docker ps -a` на каждой Docker-ноде там больше не
> собирается.

Вся статистика теперь под сущностью (снапшот `ExecutionStatsResponse` без
`group_by`, бакеты `StatsBucket` / `StatsBucketsResponse` с `group_by`):

- `GET /api/v2/nodes/stats` (`GET /nodes/stats`) и `GET /api/v2/nodes/{id}/stats`
  — статистика выполнения нод
- `GET /api/v2/commands/stats?node_id=<uuid>` (`GET /commands/stats?node_id`) и
  `GET /api/v2/commands/{id}/stats` (`GET /commands/{id}/stats`) — статистика
  команд (фильтр по ноде при `node_id`)
- `GET /api/v2/scripts/stats` и `GET /api/v2/scripts/{id}/stats` — статистика
  скриптов
- `GET /api/v2/audit/stats?group_by=hour|day|week|month`
  (`GET /audit/stats?group_by`) — статистика аудита (`?date_from`/`?date_to`
  диапазон, `?group_by` бакетирование; бакеты аудита — `{bucket,count}` и могут
  возвращаться как `BulkResult` при группировке)

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

С `group_by=hour|day|week|month` — бакеты
`{buckets:[{period,total,successful,failed,cancelled,avg_duration_ms}]}`.
Для аудита `GET /audit/stats?group_by=...` бакет — `{bucket,count}`, агрегат —
`{total, buckets:[{bucket,count}]}`; с `group_by` может возвращаться `BulkResult`.

### Примеры

```bash
  # Статистика нод — снапшот vs бакеты
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/<node-id>/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/stats?group_by=day"

  # Статистика команд — снапшот
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/<command-id>/stats"

  # Статистика команд — фильтр по ноде
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/commands/stats?node_id=<node-id>"

  # Статистика аудита — снапшот vs бакеты
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats"
curl --fail-with-body -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/audit/stats?group_by=hour&date_from=2026-09-01T00:00:00Z&date_to=2026-09-02T00:00:00Z"
```

Smoke-проверка развёртывания (см. также руководство по развёртыванию):

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/nodes/?cursor=&limit=1"
```

## Кэш OpenAPI снапшота

`scripts/openapi.snapshot.json` кэширует сгенерированную OpenAPI-спецификацию для
быстрых E2E-проверок покрытия. Пересоздайте через `make generate-openapi` или
`uv run python scripts/generate_openapi_snapshot.py`. E2E-тесты
(`tests/e2e/test_endpoint_coverage_e2e.py`) используют кэшированный снапшот,
если он есть; иначе спецификация генерируется на лету.

## SSE поток событий

Поток серверных событий доступен через `GET /api/v2/events/stream`. События:
`node.status_changed`, `execution.completed`, `execution.failed`,
`script.scheduled`, `job.progress`. Подпишитесь для мониторинга в реальном
времени без опроса.

## Экспорт аудита

Записи журнала аудита доступны для экспорта через `GET /api/v2/audit/exports`
(с cursor-пагинацией; legacy `GET /api/v2/audit/export?fmt=json|csv`
по-прежнему документирован) с параметрами `fmt=json` или `fmt=csv`. Используйте
для интеграции с SIEM или compliance-отчётности.
