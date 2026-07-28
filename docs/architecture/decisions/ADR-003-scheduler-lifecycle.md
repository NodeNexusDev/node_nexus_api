# ADR-003: Scheduler Lifecycle

Status: **Accepted**

## Context

`ScriptScheduler` is both a manual singleton and an APP-scoped DI dependency.
Its start and stop methods are not part of the production lifespan, and its
callback imports the global container.

## Considered options

1. Start the current singleton from `main.py`.
2. Manage the scheduler as a Dishka application resource.
3. Introduce an external scheduler and worker.

## Decision

Use option 2. Dishka owns one scheduler instance, starts it during resource
initialization, and stops it during finalization. Scheduled callbacks open a
fresh nested scope through an injected execution callback.

The scheduler remains in-process and in-memory.

## Consequences

- Startup and shutdown are deterministic.
- Tests can verify resource finalization.
- Jobs are lost on restart.
- Running multiple API processes is unsupported for scheduled jobs.

## Rejected alternatives

- A manual singleton duplicates DI lifecycle ownership.
- An external worker is unnecessary at the current scale.

## Revisit when

Persistent schedules or multiple API processes become required.
