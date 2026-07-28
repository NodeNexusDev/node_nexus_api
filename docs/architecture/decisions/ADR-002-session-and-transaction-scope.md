# ADR-002: Session and Transaction Scope

Status: **Accepted**

## Context

Request-scoped sessions are convenient for CRUD but can remain open during slow
SSH operations. Bulk operations may also share one session across concurrent
tasks, which SQLAlchemy does not support.

## Considered options

1. Keep one session and transaction for the entire request.
2. Give every operation an unrestricted session factory.
3. Keep request scope for short CRUD and use explicit short persistence scopes
   for remote operations.

## Decision

Use option 3. Remote operations load immutable DTOs in a short read scope, close
it before external I/O, and persist results in a separate short write scope.
Concurrent workers never access a shared session.

## Consequences

- Database connections are not held during remote waits.
- Transaction boundaries become explicit.
- Remote use cases need specialized readers/writers or a small UoW factory.
- CRUD code remains simple.

## Rejected alternatives

- Request-wide transactions mix database and network lifecycles.
- An unrestricted session factory in every service weakens ownership rules.

## Revisit when

A general-purpose transaction coordinator becomes necessary across multiple
bounded contexts.
