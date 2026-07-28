---
title: Configuration reference
status: stable
translation_key: reference.configuration
source_revision: "2026-07-29"
---

# Configuration reference

`app/core/config.py` is authoritative for names and defaults.

| Variable | Required/default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | Async SQLAlchemy database URL |
| `SECRET_KEY` | required | Credential encryption root secret |
| `DEBUG` | `false` | Development diagnostics |
| `LOG_LEVEL` | `INFO` | Application log level |
| `PORT` | `8000` | HTTP listen port |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins |
| `MASTER_API_KEY` | empty | Bootstrap read-write key |
| `ENCRYPTION_SALT` | `node-nexus-ssh-v1` | Encryption derivation salt |
| `REQUEST_TIMEOUT` | `300` | Global timeout in seconds |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per process-local window |
| `RATE_LIMIT_WINDOW` | `60` | Rate-limit window in seconds |
| `AUDIT_LOG_RETENTION_DAYS` | `90` | Audit retention; `0` disables cleanup |
| `AUTO_MIGRATE` | `true` | Apply migrations on startup |
| `PROMETHEUS_ENABLED` | `true` | Expose Prometheus metrics |
| `PROMETHEUS_PATH` | `/metrics` | Metrics path |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry |
| `OTEL_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector |
| `OTEL_SERVICE_NAME` | `node-nexus-api` | Trace service name |

Override every secret and environment-specific URL in production.
