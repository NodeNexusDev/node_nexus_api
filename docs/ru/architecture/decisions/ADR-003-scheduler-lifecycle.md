---
title: "ADR-003: Lifecycle scheduler"
status: accepted
translation_key: architecture.decisions.003
source_revision: "2026-07-29"
---

# ADR-003: Lifecycle scheduler

Canonical record: English version.

## Решение

Запускать APScheduler как один application-scoped in-memory component. Каждый
job открывает новый request scope.

## Последствия

Schedules не переживают restart, несколько scheduler replicas небезопасны.
Persistent distributed scheduling потребует нового ADR.
