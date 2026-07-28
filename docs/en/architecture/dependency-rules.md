---
title: Dependency rules
status: stable
translation_key: architecture.dependency-rules
source_revision: "2026-07-29"
---

# Dependency rules

Dependencies point inward:

```text
API/adapters -> application services -> ports and boundary DTOs
API -> legacy services -> repositories/connectors
repositories -> SQLAlchemy models
DI composition -> all concrete implementations
```

Application DTOs and ports must not import FastAPI, SQLAlchemy models,
repositories, or concrete connectors. API modules do not manage transactions.
Repositories do not call services. The composition root is the only place that
constructs the object graph. Architecture tests enforce these boundaries.
