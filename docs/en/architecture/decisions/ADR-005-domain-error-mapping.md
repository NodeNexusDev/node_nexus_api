---
title: "ADR-005: Domain error mapping"
status: accepted
translation_key: architecture.decisions.005
source_revision: "2026-07-30"
---

# ADR-005: Domain error mapping

## Decision

Domain code raises transport-agnostic errors. One API mapping translates them
to stable HTTP statuses and a JSON envelope with `code`, `message`,
`request_id`, and `detail` fields.

## Consequences

Services remain reusable and error behavior has one reviewable location.
