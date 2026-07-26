# Конфигурация

> [README](../README.md) · [API Specification](api-spec.md) · [Architecture](architecture.md) · **Configuration** · [Development](development.md)

## Переменные окружения

Все настройки в `app/core/config.py` через Pydantic Settings. Файл `.env` **не коммитится** в репозиторий.

### Основные

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | URL подключения к PostgreSQL | — |
| `SECRET_KEY` | Ключ для вывода AES-256-GCM ключа через HKDF | — |
| `MASTER_API_KEY` | Master API ключ для аутентификации | `""` |
| `PORT` | Порт сервера | `8000` |
| `CORS_ORIGINS` | Разрешённые origins (JSON массив) | `["http://localhost:3000"]` |
| `LOG_LEVEL` | Уровень логирования (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `DEBUG` | Режим отладки (включает console renderer для логов) | `false` |

### Безопасность

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `ENCRYPTION_SALT` | Соль для HKDF при шифровании паролей/SSH-ключей | `node-nexus-ssh-v1` |
| `REQUEST_TIMEOUT` | Глобальный таймаут HTTP-запроса (сек) | `300` |
| `RATE_LIMIT_REQUESTS` | Максимум запросов в окне rate limiting | `100` |
| `RATE_LIMIT_WINDOW` | Окно rate limiting (сек) | `60` |

### Аудит

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `AUDIT_LOG_RETENTION_DAYS` | Автоудаление старых записей аудит-лога (0 = отключено) | `90` |

### Поведение

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `AUTO_MIGRATE` | Автоматический запуск Alembic миграций при старте приложения | `true` |

### Observability

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `PROMETHEUS_ENABLED` | Включить `/metrics` endpoint | `true` |
| `PROMETHEUS_PATH` | Путь к Prometheus метрикам | `/metrics` |
| `OTEL_ENABLED` | Включить OpenTelemetry tracing | `false` |
| `OTEL_ENDPOINT` | OTLP gRPC endpoint | `http://localhost:4317` |
| `OTEL_SERVICE_NAME` | Имя сервиса в трейсах | `node-nexus-api` |

---

## Быстрый старт

### Через Docker (рекомендуется)

```bash
# 1. Клонировать
git clone https://github.com/NodeNexusDev/node_nexus_api.git
cd node_nexus_api

# 2. Создать .env
cp .env.example .env
# Отредактировать .env

# 3. Запустить
docker compose up -d --build
```

### Локальная разработка

```bash
# 1. Установить зависимости
uv sync

# 2. Настроить окружение
cp .env.example .env
# Отредактировать .env

# 3. Запустить PostgreSQL
docker compose up -d db

# 4. Применить миграции
uv run alembic upgrade head

# 5. Запустить сервер
uv run python -m app.main
# Или через uvicorn:
uv run uvicorn app.main:app --reload
```

---

## Docker

### docker-compose.yml (development)

- PostgreSQL + API
- PostgreSQL: порт `5432`
- API: порт `8000`
- Healthcheck API использует `MASTER_API_KEY` из переменных окружения

### tests/docker-compose.e2e.yml (E2E тесты)

- PostgreSQL + SSH-сервер + API
- Используется для полного стека тестирования

### Dockerfile

Multi-stage сборка на базе `python:3.13-slim`, пользователь `appuser`.

В образ **не попадают**: `.env`, `.git`, `tests/`, credentials.

---

## Аутентификация

Все эндпоинты API (кроме `/health` и `/ready`) требуют аутентификации через заголовок `X-API-Key`.

### Способы

1. **Master Key** — ключ из `MASTER_API_KEY`. Полный доступ (read-write).
2. **API Key** — ключ, созданный через `POST /api/v1/api-keys/`. Хранится в БД как SHA-256 хеш.

### Атрибуты API ключа

| Атрибут | Описание |
|---------|----------|
| `name` | Человекочитаемое имя |
| `scope` | `read-write` (по умолчанию) или `read-only` |
| `is_active` | Можно отозвать без удаления |
| `expires_at` | Дата истечения срока действия (опционально) |

### Пример

```
GET /api/v1/nodes/ HTTP/1.1
Host: localhost:8000
X-API-Key: nnk_abc123def456...
```

---

## Kubernetes пробы

| Endpoint | Тип | Аутентификация | Описание |
|----------|-----|:--:|----------|
| `GET /health` | Liveness | Нет | Проверяет, что процесс запущен |
| `GET /ready` | Readiness | Нет | Проверяет подключение к БД (503 если ошибка) |
| `GET /metrics` | Prometheus | Нет | Prometheus-метрики (если `PROMETHEUS_ENABLED=true`) |
