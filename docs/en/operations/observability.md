---
title: Observability
status: stable
translation_key: operations.observability
source_revision: "2026-07-29"
---

# Observability

Prometheus metrics are exposed at `PROMETHEUS_PATH` when enabled. OpenTelemetry
exports traces to `OTEL_ENDPOINT`. Structured logs cover request and lifecycle
events. Alert on readiness, error and timeout rates, latency, database failures,
and scheduler errors. Never collect API keys, SSH credentials, or private keys.

Application metrics use the `node_nexus_` prefix. Audit outbox metrics report
successful deliveries, failures, retries, pending events, and the age of the
oldest pending event. Scheduler metrics report ownership, restoration
readiness, registration failures, execution outcomes, and execution duration.
They also expose the active persistent schedule count, misfires, overlap skips,
and planned-to-observed start lag.

Alert on a growing `node_nexus_audit_pending` value, an increasing oldest
pending age, scheduler registration failures, and a scheduler readiness value
of zero. A non-owner replica normally reports `node_nexus_scheduler_owner 0`;
this alone is not a failure when another healthy replica owns the advisory lock.
