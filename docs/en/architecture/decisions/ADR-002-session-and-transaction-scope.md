---
title: "ADR-002: Session and transaction scope"
status: accepted
translation_key: architecture.decisions.002
source_revision: "2026-07-29"
---

# ADR-002: Session and transaction scope

## Decision

Use one async SQLAlchemy session per request scope. Services own transaction
completion; repositories flush but do not commit. Remote side effects are kept
outside long-running transactions.

## Consequences

Atomic CRUD is predictable, while distributed operations explicitly report
partial failure.
