---
title: "ADR-005: Domain error mapping"
status: accepted
translation_key: architecture.decisions.005
source_revision: "2026-07-29"
---

# ADR-005: Domain error mapping

## Decision

Domain code raises transport-agnostic errors. One API mapping translates them
to stable HTTP statuses and the `{"detail": "..."}` envelope.

## Consequences

Services remain reusable and error behavior has one reviewable location.
