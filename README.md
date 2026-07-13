# Node Nexus API

REST API для управления серверными нодами с SSH-подключениями.

## Стек

- **Python 3.13**, **FastAPI**, **SQLAlchemy 2.0** (async), **Alembic**
- **dishka** (DI), **asyncssh**, **cryptography** (AES-256-GCM)
- **PostgreSQL**, **Docker**

## Быстрый старт

```bash
# Установка зависимостей
uv sync

# Запуск (требуется PostgreSQL)
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Или всё через Docker
docker compose up -d --build
```

## API

Полная спецификация: [docs/api-spec.md](docs/api-spec.md)

## Безопасность

- **SSH-ключи и пароли** шифруются AES-256-GCM перед записью в БД
- Секреты **не возвращаются** в API-ответах

## Конфигурация

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | URL PostgreSQL | — |
| `SECRET_KEY` | Ключ шифрования | — |
| `LOG_LEVEL` | Уровень логирования | INFO |
| `DEBUG` | Режим отладки | false |

## Тесты

```bash
# Все тесты
uv run pytest tests/unit/ tests/integration/ -v

# С покрытием
uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing

# E2E (требует Docker)
uv run pytest tests/e2e/ -v
```

## Архитектура

```
API (FastAPI routers)
    ↓
Service (бизнес-логика)
    ↓
Repository (SQLAlchemy)
    ↓
Model (ORM)

Connectors (SSH) ← Service
Security (AES-256-GCM) ← Service
Audit Log ← Service
```

## Структура проекта

```
app/
├── api/v1/          # Эндпоинты
├── core/            # Конфигурация, безопасность, коннекторы
├── di/              # Dependency injection (dishka)
├── models/          # SQLAlchemy модели
├── repositories/    # Доступ к данным
├── schemas/         # Pydantic-схемы
└── services/        # Бизнес-логика
```

## Лицензия

[MIT](LICENSE)
