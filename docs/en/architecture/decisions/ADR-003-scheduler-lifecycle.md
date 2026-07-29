---
title: "ADR-003: Scheduler lifecycle"
status: accepted
translation_key: architecture.decisions.003
source_revision: "2026-07-30"
---

# ADR-003: Scheduler lifecycle

## Decision

PostgreSQL is the source of truth for desired schedules. APScheduler is an
application-scoped, ephemeral runtime projection behind `JobSchedulerPort`.

Schedule management validates input, persists desired state, applies the
runtime job, and records registration status. Startup and periodic
reconciliation rebuild missing jobs, replace changed jobs, and remove runtime
orphans.

The scheduler callback receives a pre-composed `ScheduledScriptExecutor`
application use case. It does not open a request scope or resolve services from
the container. Execution metadata uses short, independent writer operations.

One replica owns execution through a PostgreSQL session advisory lock. The lock
connection and ownership monitor remain infrastructure lifecycle concerns.

## Consequences

Schedules survive process restarts and runtime state converges back to the
persistent registry. Multiple replicas may serve the API, but only the current
advisory-lock owner executes scheduled jobs. APScheduler is not a second source
of truth, and readiness is reported only after successful reconciliation.
