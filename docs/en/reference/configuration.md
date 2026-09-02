---
title: Configuration reference
status: stable
translation_key: reference.configuration
source_revision: "2026-09-02"
---

# Configuration reference

`app/core/config.py` is authoritative for names and defaults.

| Variable | Required/default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | Async SQLAlchemy database URL |
| `ENVIRONMENT` | `production` | Runtime profile: `development`, `test`, or `production` |
| `SECRET_KEY` | required | Credential encryption root secret; minimum 32 characters in production; also used for JWT signing (HS256) |
| `DEBUG` | `false` | Development diagnostics |
| `LOG_LEVEL` | `INFO` | Application log level |
| `PORT` | `8000` | HTTP listen port |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins |
| `MASTER_API_KEY` | empty | Bootstrap read-write key; minimum 32 characters in production when configured |
| `ENCRYPTION_SALT` | empty | Encryption derivation salt; minimum 16 characters in production |
| `SSH_STRICT_HOST_KEY_CHECKING` | `true` | Require SSH server host key verification |
| `SSH_KNOWN_HOSTS_PATH` | `/app/.ssh/known_hosts` | Path to the OpenSSH known-hosts file |
| `SSH_KNOWN_HOSTS_AUTO_ADD` | `false` | Auto-fetch host keys via `ssh-keyscan` on node create/update/validate and refresh endpoint |
| `SSH_KNOWN_HOSTS_FETCH_TIMEOUT` | `10` | Timeout in seconds for `ssh-keyscan` |
| `SCHEDULER_ENABLED` | `true` | Enable persistent schedule execution on this deployment |
| `SCHEDULER_OWNERSHIP_POLL_SECONDS` | `5.0` | Seconds between scheduler ownership polls |
| `SCHEDULER_RECONCILIATION_INTERVAL_SECONDS` | `10.0` | Seconds between schedule reconciliation passes |
| `REQUEST_TIMEOUT` | `300` | Global timeout in seconds |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per process-local window |
| `RATE_LIMIT_WINDOW` | `60` | Rate-limit window in seconds |
| `RATE_LIMIT_MAX_CLIENTS` | `10000` | Maximum process-local client buckets retained in memory |
| `AUDIT_LOG_RETENTION_DAYS` | `90` | Audit retention; `0` disables cleanup |
| `AUTO_MIGRATE` | `true` | Apply migrations on startup |
| `PROMETHEUS_ENABLED` | `true` | Expose Prometheus metrics |
| `PROMETHEUS_PATH` | `/metrics` | Metrics path |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry |
| `OTEL_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector |
| `OTEL_SERVICE_NAME` | `node-nexus-api` | Trace service name |
| `E2E_ENABLED` | `false` | Enable E2E test harness endpoints |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | JWT access token TTL in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token TTL in days |
| `REFRESH_TOKEN_COOKIE_MAX_AGE` | `604800` | Refresh cookie `Max-Age` in seconds (7 days) |
| `INITIAL_SUPERUSER_EMAIL` | empty | Email for the first superuser (auto-created on startup) |
| `INITIAL_SUPERUSER_PASSWORD` | empty | Password for the first superuser; minimum 12 characters when configured |

Production configuration fails fast when required secret-length constraints are
not met. Override every placeholder secret and environment-specific URL before
starting the service.

> **Note:** `X-API-Version` header removed in 2.0; versioning is via URL prefix `/api/v2` only.
> `ENCRYPTION_SALT` (min 16 chars in production) and `SECRET_KEY` (min 32 chars) remain required.
