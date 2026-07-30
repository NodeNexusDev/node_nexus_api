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

## Alternatives considered

### Inline WebSocket handling in the router

Handle framing, authentication, and command logic directly in the FastAPI
WebSocket endpoint.

- **Rejected because:** the router becomes untestable without a WebSocket
  client. Command lifecycle, audit, and error handling would be coupled to
  transport, making the same logic unavailable for a future gRPC or scheduler
  streaming channel.

### Separate WebSocket microservice

Run WebSocket connections in a dedicated process with its own connection pool.

- **Rejected because:** it adds deployment complexity, an inter-process
  communication channel, and session synchronization. The current volume of
  concurrent streaming connections does not justify this overhead.

## Consequences

Transport disconnect handling remains explicit while command logic is testable
without a WebSocket server.
