---
title: "ADR-009: Политика translation parity"
status: accepted
translation_key: architecture.decisions.009
source_revision: "2026-07-29"
---

# ADR-009: Политика translation parity

Canonical record: English version.

## Решение

English задаёт canonical technical terminology и page identifiers. Russian —
полная localization. Каждая актуальная страница имеет пару и metadata.

## Последствия

CI сравнивает paths и metadata. Security и migration docs нельзя переводить
позже; для остальных follow-up нужно явное release-blocking исключение.
