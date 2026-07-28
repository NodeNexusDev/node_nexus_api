---
title: Правила зависимостей
status: stable
translation_key: architecture.dependency-rules
source_revision: "2026-07-29"
---

# Правила зависимостей

Зависимости направлены внутрь:

```text
API/adapters -> application services -> ports and boundary DTOs
API -> legacy services -> repositories/connectors
repositories -> SQLAlchemy models
DI composition -> all concrete implementations
```

Application DTOs и ports не импортируют FastAPI, SQLAlchemy models,
repositories или concrete connectors. API modules не управляют transactions.
Repositories не вызывают services. Только composition root создаёт object
graph. Границы проверяются architecture tests.
