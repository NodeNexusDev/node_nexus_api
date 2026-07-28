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

## Consequences

CI exports and validates the schema. API changes require metadata, tests, and
contract review. WebSocket protocol notes remain in Markdown.
