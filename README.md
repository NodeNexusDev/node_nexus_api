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

## Architecture

Node Nexus follows Ports & Adapters. FastAPI and scheduler callbacks invoke
application use cases through immutable DTOs; focused ports isolate SQLAlchemy,
SSH, Docker, security, and scheduler implementations. Remote I/O never holds a
database session. See the
[architecture guide](https://nodenexusdev.github.io/node_nexus_api/en/architecture/).

## License

[MIT](LICENSE)
