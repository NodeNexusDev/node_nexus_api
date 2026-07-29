---
title: "ADR-012: Atomic configuration import"
status: accepted
translation_key: architecture.decisions.012
source_revision: "2026-07-30"
---

# ADR-012: Atomic configuration import

## Decision

Treat configuration import as one multi-aggregate atomic operation. The
application validates format compatibility and calls a dedicated
`ConfigurationImporter` port with the complete immutable transfer DTO.

`SqlAlchemyConfigGateway` opens one transaction for nodes, commands, and
scripts, applies the duplicate-name policy, and returns an immutable result.
The port exposes neither repositories nor `AsyncSession`. Configuration export
uses a separate query port and bounded pagination.

Do not introduce a universal application Unit of Work for this requirement.

## Consequences

A late persistence failure rolls back earlier writes from the same payload.
The transaction may be larger than ordinary CRUD, but its ownership and scope
are explicit and limited to configuration transfer.
