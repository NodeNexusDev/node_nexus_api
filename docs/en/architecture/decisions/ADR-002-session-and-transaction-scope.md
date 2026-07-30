---
title: "ADR-002: Session and transaction scope"
status: accepted
translation_key: architecture.decisions.002
source_revision: "2026-07-30"
---

# ADR-002: Session and transaction scope

## Decision

Use a request-scoped session for request CRUD and sessionmaker-owned short
boundaries for APP gateways. Providers/gateways own transaction completion;
internal DAOs flush but do not commit. Remote side effects are kept outside
database transactions.

## Alternatives considered

### Unit of Work with generic repository

A single `UnitOfWork` protocol exposing `nodes`, `commands`, `scripts`,
`audit` repositories for every use case.

- **Rejected because:** a universal UoW grows with every entity and leaks
  persistence topology into application services. It tempts developers to
  hold sessions open across remote I/O boundaries.

### Session-per-request with remote I/O inside transaction

Open one transaction for the entire request, including SSH/Docker calls.

- **Rejected because:** remote I/O can take seconds or minutes. Holding a
  database connection and transaction open for that duration exhausts the
  connection pool, blocks other requests, and creates long-lived locks.

## Consequences

Atomic CRUD is predictable, remote operations release connections before I/O,
and specialized multi-aggregate operations can own a dedicated transaction.
