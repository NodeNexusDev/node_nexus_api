---
title: "ADR-003: Scheduler lifecycle"
status: accepted
translation_key: architecture.decisions.003
source_revision: "2026-07-29"
---

# ADR-003: Scheduler lifecycle

## Decision

Run APScheduler as one application-scoped in-memory component. Each job opens a
fresh request scope.

## Consequences

Schedules do not survive restart and multiple scheduler replicas are unsafe.
Persistent distributed scheduling requires a future ADR.
