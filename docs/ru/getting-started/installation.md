---
title: Установка
status: stable
translation_key: getting-started.installation
source_revision: "2026-07-30"
---

# Установка

## Docker Compose

```bash
git clone https://github.com/NodeNexusDev/node_nexus_api.git
cd node_nexus_api
cp .env.example .env
docker compose up -d --build
```

Перед тем как открыть доступ к сервису, задайте секреты из раздела
[конфигурации](configuration.md). Убедитесь, что запрос
`GET http://localhost:8000/health` завершается успешно.

## Локальный процесс

```bash
uv sync --all-extras
docker compose up -d db
uv run alembic upgrade head
uv run python -m app.main
```
