---
title: "ADR-007: Раздельные locale trees"
status: accepted
translation_key: architecture.decisions.007
source_revision: "2026-07-29"
---

# ADR-007: Раздельные locale trees

Canonical record: English version.

## Решение

Поддерживать независимые `docs/en` и `docs/ru` с одинаковыми относительными
путями и без runtime fallback.

## Последствия

Отсутствующий перевод ломает parity check, search использует нужный язык, а
language switching сохраняет путь страницы.
