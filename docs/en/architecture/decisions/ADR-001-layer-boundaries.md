---
title: "ADR-001: Layer boundaries"
status: accepted
translation_key: architecture.decisions.001
source_revision: "2026-07-29"
---

# ADR-001: Layer boundaries

## Decision

Keep transport, application orchestration, persistence, and infrastructure
concerns separate. Dependencies point toward application contracts. Dishka's
composition root binds concrete implementations.

## Consequences

HTTP details cannot leak into application DTOs, and persistence models cannot
become public schemas. Architecture tests enforce the rules.
