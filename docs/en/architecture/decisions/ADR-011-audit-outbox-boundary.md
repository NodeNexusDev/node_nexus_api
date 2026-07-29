---
title: "ADR-011: Audit outbox boundary"
status: accepted
translation_key: architecture.decisions.011
source_revision: "2026-07-30"
---

# ADR-011: Audit outbox boundary

## Decision

Persist audit events through an outbox instead of writing the final audit log
from business use cases. Optional result events join the request transaction.
An audit intent required before an external side effect uses an independent
short transaction and must complete before that side effect begins.

An APP-scoped worker claims pending records with `FOR UPDATE SKIP LOCKED`,
delivers each record idempotently using the outbox identifier as the audit-log
identifier, and records bounded retry state. The worker owns its sessions and
has an explicit shutdown finalizer.

## Consequences

Committed business changes do not silently lose their audit event, and required
intent survives a later remote failure. Delivery is eventually consistent and
operations must monitor pending age, failures, and exhausted retries.
