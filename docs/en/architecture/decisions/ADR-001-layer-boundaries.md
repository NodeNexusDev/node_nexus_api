---
title: "ADR-001: Layer boundaries"
status: accepted
translation_key: architecture.decisions.001
source_revision: "2026-07-30"
---

# ADR-001: Layer boundaries

## Alternatives considered

### Traditional Layered Architecture (Django-style)

Controllers → Services → Models, with no explicit port abstraction.

- **Rejected because:** services become tightly coupled to ORM and HTTP
  frameworks. Testing requires mocking ORM sessions or using test databases.
  Replacing PostgreSQL or adding a new transport (e.g., gRPC) forces changes
  across the entire stack.

### Clean Architecture (Uncle Bob)

Entities → Use Cases → Interface Adapters → Frameworks, with explicit
input/output boundaries and request/response models per use case.

- **Rejected because:** the ceremony of per-use-case request/response models
  and interactor interfaces adds friction without proportional benefit for a
  focused API project. Ports & Adapters provides the same dependency inversion
  with less indirection.
