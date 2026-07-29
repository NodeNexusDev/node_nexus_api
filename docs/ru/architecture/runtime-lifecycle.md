---
title: Runtime lifecycle
status: stable
translation_key: architecture.runtime-lifecycle
source_revision: "2026-07-29"
---

# Runtime lifecycle

Startup настраивает logging, опционально применяет миграции, инициализирует
scheduler и очищает устаревший audit. Telemetry и HTTP middleware создаются
вместе с app. Shutdown закрывает Dishka container, database engine и
application-scoped resources.

Request-scoped dependencies не выходят за свой scope. При startup приложение
получает advisory lock PostgreSQL и восстанавливает APScheduler jobs из
`script_schedules`; scheduled jobs создают новый scope. Реплика без ownership
обслуживает HTTP, но не выполняет jobs. Потеря процесса не удаляет расписания.
