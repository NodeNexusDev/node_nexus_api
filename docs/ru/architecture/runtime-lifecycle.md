---
title: Runtime lifecycle
status: stable
translation_key: architecture.runtime-lifecycle
source_revision: "2026-07-30"
---

# Runtime lifecycle

Lifecycle adapter настраивает logging, опционально применяет migrations,
связывает scheduler callback с `ScheduledScriptExecutor`, восстанавливает
persistent schedules и очищает устаревший audit. Durable audit outbox worker
является APP resource. Telemetry и HTTP middleware создаются вместе с app.

Request-scoped dependencies не выходят за свой scope. APP use cases используют
sessionmaker-owned short persistence adapters. Scheduler ownership защищён
PostgreSQL advisory lock, reconciliation восстанавливает APScheduler jobs из
persistent schedules. Реплика без ownership обслуживает HTTP, но не выполняет
jobs.

При shutdown Dishka закрывает container; APP finalizers останавливают scheduler
и audit worker и освобождают database engine.

## Запуск и жизненный цикл планировщика

```mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Migrating : AUTO_MIGRATE=true
    Starting --> Ready : AUTO_MIGRATE=false
    Migrating --> Ready : миграции применены

    Ready --> Reconciling : scheduler включён
    Reconciling --> Owner : advisory lock получен
    Reconciling --> Standby : lock у другой реплики

    Owner --> Executing : наступило время job
    Executing --> Owner : job завершён
    Executing --> Owner : job упал (записан)

    Owner --> Reconciling : периодическая сверка
    Standby --> Reconciling : периодическая сверка

    Owner --> Shutting_Down : SIGTERM
    Standby --> Shutting_Down : SIGTERM
    Shutting_Down --> [*] : finalizers отработали

    note right of Standby
        Обслуживает HTTP и schedule API.
        Не выполняет jobs.
    end note

    note right of Owner
        Обслуживает HTTP и schedule API.
        Выполняет scheduled jobs.
        Владеет PostgreSQL advisory lock.
    end note
```
