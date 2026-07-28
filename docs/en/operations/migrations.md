---
title: Migration runbook
status: stable
translation_key: operations.migrations
source_revision: "2026-07-29"
---

# Migration runbook

Back up the database, inspect `uv run alembic current` and
`uv run alembic history`, then run:

```bash
uv run alembic upgrade head
```

Verify `/ready` and application logs. Never autogenerate against production.
For a failed migration, stop the rollout and restore or use a reviewed downgrade
only when the migration explicitly supports it.
