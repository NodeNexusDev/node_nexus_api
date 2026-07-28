---
title: "ADR-007: Separate locale trees"
status: accepted
translation_key: architecture.decisions.007
source_revision: "2026-07-29"
---

# ADR-007: Separate locale trees

## Decision

Maintain independent `docs/en` and `docs/ru` trees with identical relative
paths and no runtime fallback.

## Consequences

Missing translations fail parity checks, search uses the right language, and
language switching preserves page paths.
