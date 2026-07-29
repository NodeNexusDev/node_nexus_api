---
title: "ADR-011: Audit outbox boundary"
status: accepted
translation_key: architecture.decisions.011
source_revision: "2026-07-30"
---

# ADR-011: Audit outbox boundary

Canonical record: English version.

## Решение

Сохранять audit events через outbox, а не писать финальный audit log из
business use case. Optional result event участвует в request transaction.
Required intent до external side effect использует независимую короткую
transaction и должен завершиться до начала side effect.

APP-scoped worker получает pending records через `FOR UPDATE SKIP LOCKED`,
доставляет запись idempotently, используя outbox identifier как audit-log
identifier, и сохраняет bounded retry state. Worker владеет sessions и имеет
явный shutdown finalizer.

## Последствия

Committed business change не теряет audit event, а required intent переживает
последующую remote failure. Delivery eventually consistent; необходимо
наблюдать pending age, failures и exhausted retries.
