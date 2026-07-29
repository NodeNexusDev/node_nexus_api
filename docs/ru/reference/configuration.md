---
title: Справочник конфигурации
status: stable
translation_key: reference.configuration
source_revision: "2026-07-29"
---

# Справочник конфигурации

`app/core/config.py` — источник истины для имён и defaults.

| Переменная | Обязательно/default | Назначение |
|---|---|---|
| `DATABASE_URL` | обязательно | Async SQLAlchemy database URL |
| `SECRET_KEY` | обязательно | Root secret шифрования credentials |
| `DEBUG` | `false` | Development diagnostics |
| `LOG_LEVEL` | `INFO` | Application log level |
| `PORT` | `8000` | HTTP listen port |
| `CORS_ORIGINS` | `http://localhost:3000` | Разрешённые browser origins |
| `MASTER_API_KEY` | пусто | Bootstrap read-write key |
| `ENCRYPTION_SALT` | `node-nexus-ssh-v1` | Salt derivation шифрования |
| `SSH_STRICT_HOST_KEY_CHECKING` | `true` | Обязательная проверка host key SSH-сервера |
| `SSH_KNOWN_HOSTS_PATH` | `/app/.ssh/known_hosts` | Путь к файлу OpenSSH `known_hosts` |
| `SCHEDULER_ENABLED` | `true` | Включить выполнение персистентных расписаний |
| `REQUEST_TIMEOUT` | `300` | Global timeout в секундах |
| `RATE_LIMIT_REQUESTS` | `100` | Requests на process-local window |
| `RATE_LIMIT_WINDOW` | `60` | Rate-limit window в секундах |
| `AUDIT_LOG_RETENTION_DAYS` | `90` | Retention audit; `0` отключает cleanup |
| `AUTO_MIGRATE` | `true` | Миграции при startup |
| `PROMETHEUS_ENABLED` | `true` | Включить Prometheus metrics |
| `PROMETHEUS_PATH` | `/metrics` | Metrics path |
| `OTEL_ENABLED` | `false` | Включить OpenTelemetry |
| `OTEL_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector |
| `OTEL_SERVICE_NAME` | `node-nexus-api` | Trace service name |

В production переопределите все secrets и environment-specific URLs.
