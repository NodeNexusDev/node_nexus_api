---
title: "ADR-002: Session и transaction scope"
status: accepted
translation_key: architecture.decisions.002
source_revision: "2026-07-29"
---

# ADR-002: Session и transaction scope

Canonical record: English version.

## Решение

Использовать одну async SQLAlchemy session на request scope. Services завершают
transaction; repositories выполняют flush без commit. Remote side effects
находятся вне долгих transactions.

## Последствия

Atomic CRUD предсказуем, distributed operations явно сообщают partial failure.
