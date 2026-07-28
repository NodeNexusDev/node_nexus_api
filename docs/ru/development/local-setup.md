---
title: Локальная настройка
status: stable
translation_key: development.local-setup
source_revision: "2026-07-29"
---

# Локальная настройка

```bash
uv sync --all-extras
cp .env.example .env
docker compose up -d db
uv run alembic upgrade head
uv run python -m app.main
```

Используйте не-production secrets. Swagger UI доступен на `/docs`, ReDoc на
`/redoc`, machine-readable contract — на `/openapi.json`.
