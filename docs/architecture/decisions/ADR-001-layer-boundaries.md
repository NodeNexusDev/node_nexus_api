# ADR-001: Layer Boundaries

Status: **Accepted**

## Context

The project has a useful layered structure, but some HTTP and WebSocket adapters
access repositories and ORM state directly. Existing documentation also claims a
stricter dependency inversion model than the implementation provides.

## Considered options

1. Keep informal layers without enforcement.
2. Adopt a full domain-driven architecture for every CRUD operation.
3. Use pragmatic ports and DTOs only at important infrastructure boundaries.

## Decision

Use option 3. Keep the modular monolith and existing CRUD services. Introduce
application ports and immutable DTOs for SSH, Docker, scheduler, WebSocket, bulk,
and other long-running use cases. Enforce dependency direction automatically.

## Consequences

- Critical boundaries become explicit and testable.
- Simple CRUD avoids unnecessary abstraction.
- Migration can be incremental.
- Some existing services temporarily depend on concrete repositories.

## Rejected alternatives

- Informal boundaries continue current architectural drift.
- Full clean architecture would add excessive mapping and interfaces for this
  project size.

## Revisit when

The project gains independently deployed modules or substantially different
persistence implementations.
