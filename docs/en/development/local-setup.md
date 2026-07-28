---
title: Local setup
status: stable
translation_key: development.local-setup
source_revision: "2026-07-29"
---

# Local setup

```bash
uv sync --all-extras
cp .env.example .env
docker compose up -d db
uv run alembic upgrade head
uv run python -m app.main
```

Use non-production secrets. Swagger UI is at `/docs`, ReDoc at `/redoc`, and
the machine-readable contract at `/openapi.json`.
