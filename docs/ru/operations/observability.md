---
title: Наблюдаемость
status: stable
translation_key: operations.observability
source_revision: "2026-08-17"
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
`request_id`, что позволяет связывать клиентские ошибки с серверными логами.

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

## Dashboard

Агрегированный обзор системы доступен через `GET /api/v2/dashboard/`. Эндпоинт
возвращает статистику по нодам, Docker-контейнерам, скриптам, командам и
последним действиям в журнале аудита.

```bash
curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v2/dashboard/"
```

### Ответ

```json
{
  "nodes": {
    "total": 12,
    "active": 10,
    "unreachable": 2
  },
  "docker": {
    "total": 25,
    "running": 18,
    "stopped": 7
  },
  "scripts": {
    "total": 8
  },
  "commands": {
    "total": 15
  },
  "recent_activity": [
    {
      "id": "...",
      "action": "create",
      "node_id": "...",
      "user": "admin",
      "details": "{\"name\": \"web-1\"}",
      "created_at": "2026-08-16T10:00:00Z"
    }
  ]
}
```

### Поля

| Поле | Описание |
|------|----------|
| `nodes.total` | Общее количество нод |
| `nodes.active` | Ноды со статусом `active` |
| `nodes.unreachable` | Ноды со статусом `unreachable` |
| `docker.total` | Общее количество Docker-контейнеров на всех Docker-нодах |
| `docker.running` | Запущенные контейнеры |
| `docker.stopped` | Остановленные контейнеры |
| `scripts.total` | Количество скриптов |
| `commands.total` | Количество команд |
| `recent_activity` | Последние 10 записей журнала аудита |

Docker-статистика собирается путём выполнения `docker ps -a` на каждой
Docker-ноде. Если нода недоступна, её контейнеры не учитываются (ошибки
обрабатываются грациозно).

## Метрики дашборда

Временные ряды метрик выполнения доступны через `GET /api/v2/dashboard/metrics`.
Поддерживаются гранулярности `hour`, `day`, `week`, `month` с фильтрами
`date_from` и `date_to`. Возвращаются метрики команд и скриптов с полями
`total`, `success`, `failure` для каждого бакета.

## SSE поток событий

Поток серверных событий доступен через `GET /api/v2/events/stream`. События:
`node.status_changed`, `execution.completed`, `execution.failed`,
`script.scheduled`, `job.progress`. Подпишитесь для мониторинга в реальном
времени без опроса.

## Экспорт аудита

Записи журнала аудита доступны для экспорта через `GET /api/v2/audit/export`
с параметрами `fmt=json` или `fmt=csv`. Используйте для интеграции с SIEM
или compliance-отчётности.
