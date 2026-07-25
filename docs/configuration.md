# Конфигурация

> [README](../README.md) · [API Specification](api-spec.md) · [Architecture](architecture.md) · **Configuration** · [Development](development.md)

## Переменные окружения

Все настройки в `app/core/config.py` через Pydantic Settings. Файл `.env` **не коммитится** в репозиторий.

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | URL подключения к PostgreSQL | — |
| `SECRET_KEY` | Ключ для вывода AES-256-GCM ключа через HKDF | — |
| `MASTER_API_KEY` | Master API ключ для аутентификации | — |
| `PORT` | Порт сервера | `8000` |
| `CORS_ORIGINS` | Разрешённые origins (JSON массив) | `["http://localhost:3000"]` |
| `LOG_LEVEL` | Уровень логирования (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `DEBUG` | Режим отладки | `false` |
| `ENCRYPTION_SALT` | Соль для HKDF (шифрование) | `node-nexus-ssh-v1` |

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

### tests/docker-compose.e2e.yml (E2E тесты)

- PostgreSQL + SSH-сервер + API
- Используется для полного стека тестирования

### Dockerfile

Multi-stage сборка на базе `python:3.13-slim`, пользователь `appuser`.

В образ **не попадают**: `.env`, `.git`, `tests/`, credentials.

---

## Аутентификация

Все эндпоинты API требуют аутентификации через заголовок `X-API-Key`.

### Способы

1. **Master Key** — ключ из `MASTER_API_KEY`. Полный доступ.
2. **API Key** — ключ, созданный через `/api/v1/api-keys/`. Хранится в БД как SHA-256 хеш.

### Пример

```
GET /api/v1/nodes/ HTTP/1.1
Host: localhost:8000
X-API-Key: nnk_abc123def456...
```
