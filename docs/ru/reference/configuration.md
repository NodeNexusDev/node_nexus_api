---
title: Справочник конфигурации
status: stable
translation_key: reference.configuration
source_revision: "2026-08-26"
---

# Справочник конфигурации

`app/core/config.py` — источник истины для имён и defaults.

| Переменная | Обязательно/default | Назначение |
|---|---|---|
| `DATABASE_URL` | обязательно | Async SQLAlchemy database URL |
| `SECRET_KEY` | обязательно | Root secret шифрования credentials; также используется для подписи JWT (HS256) |
| `DEBUG` | `false` | Development diagnostics |
| `LOG_LEVEL` | `INFO` | Application log level |
| `PORT` | `8000` | HTTP listen port |
| `CORS_ORIGINS` | `http://localhost:3000` | Разрешённые browser origins |
| `MASTER_API_KEY` | пусто | Bootstrap read-write key |
| `ENCRYPTION_SALT` | пусто | Salt derivation шифрования (обязательно в production) |
| `SSH_STRICT_HOST_KEY_CHECKING` | `true` | Обязательная проверка host key SSH-сервера |
| `SSH_KNOWN_HOSTS_PATH` | `/app/.ssh/known_hosts` | Путь к файлу OpenSSH `known_hosts` |
| `SCHEDULER_ENABLED` | `true` | Включить выполнение персистентных расписаний |
| `SCHEDULER_OWNERSHIP_POLL_SECONDS` | `5.0` | Интервал опроса владельца планировщика (сек) |
| `SCHEDULER_RECONCILIATION_INTERVAL_SECONDS` | `10.0` | Интервалconciliation расписаний (сек) |
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
| `SUPPORTED_API_VERSIONS` | `["1"]` | Поддерживаемые версии API |
| `E2E_ENABLED` | `false` | Включить endpoints E2E test harness |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | TTL access token JWT (минуты) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | TTL refresh token JWT (дни) |
| `REFRESH_TOKEN_COOKIE_MAX_AGE` | `604800` | Max-Age refresh cookie (секунды, 7 дней) |
| `INITIAL_SUPERUSER_EMAIL` | пусто | Email первого суперпользователя (авто-создание при startup) |
| `INITIAL_SUPERUSER_PASSWORD` | пусто | Пароль первого суперпользователя |

В production переопределите все secrets и environment-specific URLs.
