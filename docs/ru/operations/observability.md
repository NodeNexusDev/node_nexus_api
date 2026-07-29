---
title: Наблюдаемость
status: stable
translation_key: operations.observability
source_revision: "2026-07-29"
---

# Наблюдаемость

Prometheus metrics доступны по `PROMETHEUS_PATH`, если включены. OpenTelemetry
отправляет traces в `OTEL_ENDPOINT`. Структурированные логи содержат request и
lifecycle events. Настройте alerts на readiness, долю ошибок и timeout, latency,
ошибки БД и scheduler. Не собирайте API keys, SSH credentials и private keys.

Прикладные метрики используют префикс `node_nexus_`. Метрики audit outbox
показывают успешные доставки, ошибки, повторные попытки, количество ожидающих
событий и возраст самого старого события. Метрики scheduler отражают ownership,
готовность восстановления, ошибки регистрации, результаты и длительность
выполнений. Дополнительно доступны количество активных персистентных
расписаний, misfire, пропуски из-за overlap и задержка относительно планового
времени запуска.

Настройте alerts на рост `node_nexus_audit_pending`, увеличение возраста
старейшего события, ошибки регистрации расписаний и нулевую готовность
scheduler. Значение `node_nexus_scheduler_owner 0` у non-owner реплики само по
себе не является ошибкой, если advisory lock удерживает другая исправная
реплика.
