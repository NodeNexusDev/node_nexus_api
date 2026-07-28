---
title: "ADR-008: HTTP contract в OpenAPI"
status: accepted
translation_key: architecture.decisions.008
source_revision: "2026-07-29"
---

# ADR-008: HTTP contract в OpenAPI

Canonical record: English version.

## Решение

Сгенерированный FastAPI OpenAPI — единственный полный contract endpoints и
schemas. Markdown объясняет concepts и workflows без дублирования таблиц.

## Последствия

CI экспортирует и валидирует schema. Изменения API требуют metadata, tests и
contract review. WebSocket protocol остаётся в Markdown.
