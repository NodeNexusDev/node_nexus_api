---
title: "ADR-005: Domain error mapping"
status: accepted
translation_key: architecture.decisions.005
source_revision: "2026-07-29"
---

# ADR-005: Domain error mapping

Canonical record: English version.

## Решение

Domain code создаёт transport-agnostic errors. Единый API mapping переводит их
в стабильные HTTP statuses и envelope `{"detail": "..."}`.

## Последствия

Services остаются переиспользуемыми, error behavior имеет одно место проверки.
