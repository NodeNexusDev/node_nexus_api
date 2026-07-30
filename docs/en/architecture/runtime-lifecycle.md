---
title: Runtime lifecycle
status: stable
translation_key: architecture.runtime-lifecycle
source_revision: "2026-07-30"
---

# Runtime lifecycle

The lifecycle adapter configures logging, optionally applies migrations, binds
the scheduler callback to `ScheduledScriptExecutor`, restores persistent
schedules, and cleans expired audit records. The durable audit outbox worker is
an APP resource. Telemetry and HTTP middleware are configured when the app is
created.

Request-scoped dependencies never escape their scope. APP use cases use
sessionmaker-owned short persistence adapters. Scheduler ownership is protected
by a PostgreSQL advisory lock, and reconciliation rebuilds APScheduler jobs from
persistent schedules. A non-owner replica serves HTTP but never executes jobs.

Shutdown closes the Dishka container; APP finalizers stop the scheduler and
audit worker and dispose the database engine.

## Startup and scheduler lifecycle

```mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Migrating : AUTO_MIGRATE=true
    Starting --> Ready : AUTO_MIGRATE=false
    Migrating --> Ready : migrations applied

    Ready --> Reconciling : scheduler enabled
    Reconciling --> Owner : advisory lock acquired
    Reconciling --> Standby : lock held by another replica

    Owner --> Executing : next job due
    Executing --> Owner : job complete
    Executing --> Owner : job failed (recorded)

    Owner --> Reconciling : periodic reconciliation
    Standby --> Reconciling : periodic reconciliation

    Owner --> Shutting Down : SIGTERM
    Standby --> Shutting Down : SIGTERM
    Shutting Down --> [*] : finalizers run

    note right of Standby
        Serves HTTP and schedule API.
        Does not execute jobs.
    end note

    note right of Owner
        Serves HTTP and schedule API.
        Executes scheduled jobs.
        Holds PostgreSQL advisory lock.
    end note
```
