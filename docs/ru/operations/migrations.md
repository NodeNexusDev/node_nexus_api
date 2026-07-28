---
title: Runbook миграций
status: stable
translation_key: operations.migrations
source_revision: "2026-07-29"
---

# Runbook миграций

Создайте backup БД, проверьте `uv run alembic current` и
`uv run alembic history`, затем выполните:

```bash
uv run alembic upgrade head
```

Проверьте `/ready` и логи. Не запускайте autogenerate на production. При ошибке
остановите rollout и восстановите backup либо примените проверенный downgrade,
если миграция явно его поддерживает.
