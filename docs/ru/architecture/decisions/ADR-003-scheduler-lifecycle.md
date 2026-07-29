---
title: "ADR-003: Lifecycle scheduler"
status: accepted
translation_key: architecture.decisions.003
source_revision: "2026-07-30"
---

# ADR-003: Lifecycle scheduler

Canonical record: English version.

## Решение

PostgreSQL является источником истины для desired schedules. APScheduler —
application-scoped эфемерная runtime-проекция за `JobSchedulerPort`.

Управление расписанием валидирует входные данные, сохраняет desired state,
применяет runtime job и записывает результат регистрации. Startup и
периодическая reconciliation восстанавливают отсутствующие jobs, заменяют
изменённые и удаляют runtime orphans.

Scheduler callback получает заранее собранный application use case
`ScheduledScriptExecutor`. Он не открывает request scope и не ищет сервисы в
container. Метаданные выполнения записываются короткими независимыми writer
operations.

Одна реплика владеет выполнением через PostgreSQL session advisory lock.
Соединение lock и ownership monitor остаются infrastructure lifecycle concerns.

## Последствия

Расписания переживают restart процесса, а runtime state сходится к persistent
registry. Несколько реплик могут обслуживать API, но scheduled jobs выполняет
только текущий владелец advisory lock. APScheduler не является вторым источником
истины, а readiness публикуется только после успешной reconciliation.
