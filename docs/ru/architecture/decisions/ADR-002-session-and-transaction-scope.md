---
title: "ADR-002: Session и transaction scope"
status: accepted
translation_key: architecture.decisions.002
source_revision: "2026-07-30"
---

# ADR-002: Session и transaction scope

Canonical record: English version.

## Решение

Для request CRUD использовать request-scoped session, для APP gateways —
короткие boundaries через sessionmaker. Provider/gateway завершает transaction,
внутренний DAO выполняет flush без commit. Remote side effects находятся вне
DB transaction.

## Последствия

Atomic CRUD предсказуем, remote operation освобождает connection до I/O, а
специализированная multi-aggregate operation может владеть отдельной
transaction.
