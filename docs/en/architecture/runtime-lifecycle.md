---
title: Runtime lifecycle
status: stable
translation_key: architecture.runtime-lifecycle
source_revision: "2026-07-29"
---

# Runtime lifecycle

Startup configures logging, optionally applies migrations, initializes the
scheduler, and cleans expired audit records. Telemetry and HTTP middleware are
configured when the app is created. Shutdown closes the Dishka container,
database engine, and application-scoped resources.

Request-scoped dependencies must never escape their scope. Startup acquires a
PostgreSQL advisory lock and rebuilds APScheduler jobs from persistent
`script_schedules`; scheduled jobs create a fresh scope. A non-owner replica
serves HTTP but never executes jobs. Losing process ownership does not lose
schedule definitions.
