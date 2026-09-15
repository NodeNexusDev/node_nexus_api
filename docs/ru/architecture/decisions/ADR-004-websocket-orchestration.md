---
title: "ADR-004: WebSocket orchestration"
status: accepted
translation_key: architecture.decisions.004
source_revision: "2026-09-09"
---

# ADR-004: WebSocket orchestration

Canonical record: English version.

## Решение

Оставить WebSocket framing в API adapter, а orchestration streaming-команды —
в application service за ports.

## Последствия

Обработка disconnect остаётся явной, command logic тестируется без WebSocket
server.
