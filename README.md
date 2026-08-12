# Node Nexus API

[![CI](https://github.com/NodeNexusDev/node_nexus_api/actions/workflows/ci.yml/badge.svg)](https://github.com/NodeNexusDev/node_nexus_api/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](.agents/workflow.md)
[![Version](https://img.shields.io/badge/version-0.8.0-blue)](https://github.com/NodeNexusDev/node_nexus_api)
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

- Node inventory, tags, search, pagination, SSH checks, and system metrics
- Parameterized command templates and multi-node script pipelines
- Remote Docker container, image, network, and volume operations
- API key scopes, audit log, encrypted SSH credentials, and rate limiting
- WebSocket command output, Prometheus metrics, and OpenTelemetry tracing
- Configuration import/export without secret material

## Quick start

```bash
git clone https://github.com/NodeNexusDev/node_nexus_api.git && cd node_nexus_api

cp .env.example .env
docker compose up -d --build
```

Set strong `SECRET_KEY` and `MASTER_API_KEY` values before exposing the service.

Explore the API at `http://localhost:8000/docs` (Swagger UI) or
`http://localhost:8000/redoc` (ReDoc).

## API at a glance

```bash
# List nodes
curl -H 'X-API-Key: your-key' 'http://localhost:8000/api/v1/nodes/'

# Execute a command on a node
curl -X POST -H 'X-API-Key: your-key' \
  -H 'Content-Type: application/json' \
  -d '{"command": "uptime"}' \
  'http://localhost:8000/api/v1/nodes/{id}/execute/'
```

## Architecture

Node Nexus follows Ports & Adapters. FastAPI and scheduler callbacks invoke
application use cases through immutable DTOs; focused ports isolate SQLAlchemy,
SSH, Docker, security, and scheduler implementations. Remote I/O never holds a
database session. See the
[architecture guide](https://nodenexusdev.github.io/node_nexus_api/en/architecture/).

## Development

```bash
uv sync
uv run pytest tests/unit/ tests/integration/ -q
uv run python -m app.main
```

See the [development guide](https://nodenexusdev.github.io/node_nexus_api/en/development/)
and [architecture decisions](https://nodenexusdev.github.io/node_nexus_api/en/architecture/decisions/).

## License

[MIT](LICENSE)
