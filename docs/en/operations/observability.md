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
