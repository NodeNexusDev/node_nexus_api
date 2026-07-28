---
title: "ADR-001: Границы слоёв"
status: accepted
translation_key: architecture.decisions.001
source_revision: "2026-07-29"
---

# ADR-001: Границы слоёв

Canonical record: English version.

## Решение

Разделять transport, application orchestration, persistence и infrastructure.
Зависимости направлены к application contracts. Dishka composition root
связывает concrete implementations.

## Последствия

HTTP details не попадают в application DTO, а persistence models не становятся
public schemas. Правила контролируют architecture tests.
