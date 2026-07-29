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

## Consequences

Atomic CRUD is predictable, remote operations release connections before I/O,
and specialized multi-aggregate operations can own a dedicated transaction.
