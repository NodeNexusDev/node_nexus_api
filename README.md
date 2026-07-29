# Node Nexus API

REST API for centrally managing server nodes, SSH commands, reusable scripts,
and remote Docker resources.

**[Documentation](https://nodenexusdev.github.io/node_nexus_api/)**

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

## Documentation

- [English documentation](docs/en/index.md)
- [Документация на русском](docs/ru/index.md)
- Runtime API contract: `/docs`, `/redoc`, and `/openapi.json`

The in-process scheduler is single-owner and non-persistent. See the operations
guide before deploying multiple API replicas.

## License

[MIT](LICENSE)
