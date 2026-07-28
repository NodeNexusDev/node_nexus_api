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

Request-scoped dependencies must never escape their scope. Scheduled jobs create
a fresh scope. The scheduler stores jobs in memory, has no leader election, and
must have one owner in a multi-replica deployment.
