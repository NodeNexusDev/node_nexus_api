# ADR-004: WebSocket Orchestration

Status: **Accepted**

## Context

The WebSocket adapter currently reads repositories, decrypts credentials, creates
connectors, and imports the global DI container. This combines protocol handling,
application orchestration, and infrastructure access.

## Considered options

1. Keep orchestration in the WebSocket endpoint.
2. Move all protocol handling into a service.
3. Keep protocol handling in the adapter and move node/SSH orchestration into an
   application service.

## Decision

Use option 3. The endpoint owns authentication, WebSocket messages, and close
codes. A streaming application service owns node resolution, connector lifecycle,
streaming execution, domain errors, and audit.

Dishka manages `SESSION` and nested `REQUEST` scopes; the endpoint does not import
the global container.

## Consequences

- Credentials and ORM details leave the API layer.
- Streaming logic can be tested without FastAPI.
- Typed streaming events define the adapter/service contract.

## Rejected alternatives

- Keeping the endpoint unchanged preserves the layer violation.
- Moving WebSocket protocol concerns into the service couples the application
  layer to FastAPI.

## Revisit when

Multiple streaming transports need to share the same use case.
