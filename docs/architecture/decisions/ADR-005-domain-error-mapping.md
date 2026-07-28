# ADR-005: Domain Error Mapping

Status: **Accepted**

## Context

Routers locally translate domain errors while `main.py` also defines a global
handler. Duplicate mappings can return different statuses for the same error.

## Considered options

1. Keep mapping in every router.
2. Map all domain errors in one global registry.
3. Let services raise `HTTPException`.

## Decision

Use option 2. Domain services raise domain errors. A single API registry maps
exact domain error types to HTTP status codes and response payloads. Routers catch
errors only when they add use-case-specific behavior.

## Consequences

- Error responses are consistent.
- Routers become smaller.
- Mapping tests cover all domain error types.
- Expected client errors can use an appropriate log level.

## Rejected alternatives

- Per-router mappings drift over time.
- `HTTPException` in services couples business logic to FastAPI.

## Revisit when

The API introduces transport-specific error documents or multiple protocols with
different mapping requirements.
