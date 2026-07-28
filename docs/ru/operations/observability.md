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
