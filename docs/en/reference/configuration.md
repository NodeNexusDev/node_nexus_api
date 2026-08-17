---
title: Configuration reference
status: stable
translation_key: reference.configuration
source_revision: "2026-08-17"
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
| `ENCRYPTION_SALT` | empty | Encryption derivation salt (required in production) |
| `SSH_STRICT_HOST_KEY_CHECKING` | `true` | Require SSH server host key verification |
| `SSH_KNOWN_HOSTS_PATH` | `/app/.ssh/known_hosts` | Path to the OpenSSH known-hosts file |
| `SCHEDULER_ENABLED` | `true` | Enable persistent schedule execution on this deployment |
| `SCHEDULER_OWNERSHIP_POLL_SECONDS` | `5.0` | Seconds between scheduler ownership polls |
| `SCHEDULER_RECONCILIATION_INTERVAL_SECONDS` | `10.0` | Seconds between schedule reconciliation passes |
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
| `SUPPORTED_API_VERSIONS` | `["1"]` | Accepted API versions |
| `E2E_ENABLED` | `false` | Enable E2E test harness endpoints |

Override every secret and environment-specific URL in production.
