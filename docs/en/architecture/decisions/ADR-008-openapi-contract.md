---
title: "ADR-008: OpenAPI HTTP contract"
status: accepted
translation_key: architecture.decisions.008
source_revision: "2026-07-29"
---

# ADR-008: OpenAPI HTTP contract

## Decision

FastAPI-generated OpenAPI is the only complete HTTP endpoint and schema
contract. Markdown explains concepts and workflows without duplicating tables.

## Alternatives considered

### Hand-maintained API reference tables

Keep Markdown tables of endpoints, parameters, and responses.

- **Rejected because:** tables drift from code immediately. A new field or
  status code requires manual synchronization across multiple pages and both
  languages. OpenAPI generated from route decorators and Pydantic models is
  always accurate.

### OpenAPI as the only documentation

Publish only `/openapi.json`, `/docs`, and `/redoc` without narrative guides.

- **Rejected because:** OpenAPI describes the contract but not the workflow.
  Users need task-oriented guides (how to rotate a key, how to troubleshoot
  503) that reference the contract without duplicating it.

## Consequences

CI exports and validates the schema. API changes require metadata, tests, and
contract review. WebSocket protocol notes remain in Markdown.
