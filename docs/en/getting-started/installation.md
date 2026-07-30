---
title: Installation
status: stable
translation_key: getting-started.installation
source_revision: "2026-07-30"
---

# Installation

## Docker Compose

```bash
git clone https://github.com/NodeNexusDev/node_nexus_api.git
cd node_nexus_api
cp .env.example .env
docker compose up -d --build
```

Set the secrets described in [configuration](configuration.md) before exposing
the service. Verify `GET http://localhost:8000/health` returns a successful
response.

## Local process

```bash
uv sync --all-extras
docker compose up -d db
uv run alembic upgrade head
uv run python -m app.main
```
