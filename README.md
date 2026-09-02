# Node Nexus API

[![CI](https://github.com/NodeNexusDev/node_nexus_api/actions/workflows/ci.yml/badge.svg)](https://github.com/NodeNexusDev/node_nexus_api/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)](.agents/workflow.md)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/NodeNexusDev/node_nexus_api)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

REST API for centrally managing server nodes, SSH commands, reusable scripts,
and remote Docker resources.

**[Full documentation](https://nodenexusdev.github.io/node_nexus_api/)**
| **[API Reference](https://nodenexusdev.github.io/node_nexus_api/en/reference/api/)**
| **[OpenAPI Spec](https://nodenexusdev.github.io/node_nexus_api/en/reference/openapi.html)**

## What is Node Nexus?

Node Nexus is a control plane for server infrastructure. It provides a single
API to manage multiple remote servers: run SSH commands, execute script
pipelines, manage Docker containers, and monitor system metrics — all with
encrypted credentials, audit logging, and fine-grained API keys.

## Features

- Node inventory, tags, search, cursor pagination, SSH checks, and system metrics
- Parameterized command templates and multi-node script pipelines
- Remote Docker container, image, network, and volume operations with vertical bulk and 9 new operations
- API key scopes, audit log, encrypted SSH credentials, and rate limiting
- WebSocket command output, Prometheus metrics, and OpenTelemetry tracing
- Configuration import/export without secret material
- Favorites, tag management, command/script cloning
- Execution statistics with unified stats (snapshot and buckets) and success rate
- Audit export (JSON/CSV) and SSE metrics stream
- Bulk-first operations with BulkResult 207 Multi-Status (`{total,succeeded,failed,results}`)
- Docker Compose project lifecycle (persistent `compose_projects`)
- Template registries, packs, and installations with versioned assets

## Quick start

```bash
git clone https://github.com/NodeNexusDev/node_nexus_api.git && cd node_nexus_api

cp .env.example .env
docker compose pull && docker compose up -d
# pin version: IMAGE_TAG=2.0.0 docker compose up -d
# build from source: docker compose -f docker-compose.build.yml up -d --build
```

Set strong `SECRET_KEY` and `MASTER_API_KEY` values before exposing the service.

Explore the API at `http://localhost:8000/docs` (Swagger UI) or
`http://localhost:8000/redoc` (ReDoc).

## API at a glance

```bash
# List nodes (cursor pagination)
curl -H 'X-API-Key: your-key' 'http://localhost:8000/api/v2/nodes/?cursor=&limit=20'

# Bulk create nodes
curl -X POST -H 'X-API-Key: your-key' \
  -H 'Content-Type: application/json' \
  -d '{"items": [{"name": "srv", "host": "192.0.2.10", "port": 22, "connection_type": "ssh", "username": "ops", "password": "..."}]}' \
  'http://localhost:8000/api/v2/nodes/'

# Execute commands on nodes (M×N)
curl -X POST -H 'X-API-Key: your-key' \
  -H 'Content-Type: application/json' \
  -d '{"command_ids": ["<cmd-id>"], "node_ids": ["<node-id>"]}' \
  'http://localhost:8000/api/v2/commands/executions'
```

## Architecture

Node Nexus follows Ports & Adapters. FastAPI and scheduler callbacks invoke
application use cases through immutable DTOs; focused ports isolate SQLAlchemy,
SSH, Docker, security, and scheduler implementations. Remote I/O never holds a
database session. See the
[architecture guide](https://nodenexusdev.github.io/node_nexus_api/en/architecture/).

## Development

Dependencies are pinned via `uv.lock` (committed).

```bash
uv sync
uv run pytest tests/unit/ tests/integration/ -q
uv run python -m app.main
```

See the [development guide](https://nodenexusdev.github.io/node_nexus_api/en/development/)
and [architecture decisions](https://nodenexusdev.github.io/node_nexus_api/en/architecture/decisions/).

## License

[MIT](LICENSE)
