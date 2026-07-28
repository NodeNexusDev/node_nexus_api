---
title: Создание миграций
status: stable
translation_key: development.migrations
source_revision: "2026-07-29"
---

# Создание миграций

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Проверьте generated code, constraints, indexes, преобразование данных и
downgrade. Тестируйте на пустой БД и на предыдущем состоянии схемы.
