---
title: "ADR-010: Focused application ports"
status: accepted
translation_key: architecture.decisions.010
source_revision: "2026-07-30"
---

# ADR-010: Focused application ports

## Decision

Define ports around one use-case context and split reads from writes when their
consumers differ. Ports exchange immutable application DTOs and domain values.
They never expose ORM models, Pydantic transport schemas, sessions, concrete
connectors, or a registry of repositories.

Bind each port explicitly to an adapter in the Dishka composition root with
`provides=Port`. One adapter may implement several focused ports.

## Consequences

Use cases depend only on the capabilities they need, tests can replace one
boundary directly, and persistence topology remains private. More small
protocols and explicit bindings are accepted in exchange for stable boundaries.
