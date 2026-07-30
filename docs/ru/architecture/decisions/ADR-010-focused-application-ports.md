---
title: "ADR-010: Focused application ports"
status: accepted
translation_key: architecture.decisions.010
source_revision: "2026-07-30"
---

# ADR-010: Focused application ports

Canonical record: English version.

## Решение

Определять port вокруг одного use-case context и разделять read/write, если их
потребители различаются. Ports обмениваются immutable application DTO и domain
values. Они не раскрывают ORM models, Pydantic transport schemas, sessions,
concrete connectors или registry repositories.

Каждый port явно связывается с adapter в Dishka composition root через
`provides=Port`. Один adapter может реализовать несколько focused ports.

## Последствия

Use case зависит только от нужных capabilities, тест заменяет одну boundary, а
persistence topology остаётся private. Дополнительные небольшие protocols и
явные bindings принимаются ради стабильных границ.
