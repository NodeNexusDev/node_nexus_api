---
title: Creating migrations
status: stable
translation_key: development.migrations
source_revision: "2026-07-29"
---

# Creating migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Review generated code, constraints, indexes, data conversion, and downgrade.
Test against both an empty database and the previous schema state.
