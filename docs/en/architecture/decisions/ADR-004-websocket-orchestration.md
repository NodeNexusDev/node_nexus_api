---
title: "ADR-004: WebSocket orchestration"
status: accepted
translation_key: architecture.decisions.004
source_revision: "2026-07-29"
---

# ADR-004: WebSocket orchestration

## Decision

Keep WebSocket framing in the API adapter and command streaming orchestration in
an application service behind ports.

## Consequences

Transport disconnect handling remains explicit while command logic is testable
without a WebSocket server.
