# Node Nexus API

REST API для управления серверными нодами с SSH-подключениями.

## Стек

- **Python 3.13**, **FastAPI**, **SQLAlchemy 2.0** (async), **Alembic**
- **dishka** (DI), **asyncssh**, **cryptography** (AES-256-GCM)
- **structlog** (структурное логирование), **httpx** (async HTTP)
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

### Эндпоинты

| Ресурс | Описание |
|--------|----------|
| `/api/v1/nodes` | CRUD ноды + SSH-команды (check, execute) |
| `/api/v1/commands` | Шаблоны команд с параметрами + выполнение |
| `/api/v1/scripts` | Пайплайны команд (скрипты) + выполнение на нодах |
| `/api/v1/audit` | Просмотр аудит-лога |
| `/health` | Healthcheck |

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
| `PORT` | Порт сервера | 8000 |
| `CORS_ORIGINS` | Разрешённые origins | `["http://localhost:3000"]` |

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
Template (рендер команд) ← Service
Audit Log ← Service
Middleware (request logging) → API
```

## Структура проекта

```
app/
├── api/
│   ├── v1/
│   │   ├── nodes.py        # CRUD + SSH-команды для нод
│   │   ├── commands.py     # Шаблоны команд с параметрами
│   │   ├── scripts.py      # Пайплайны команд (скрипты)
│   │   ├── audit.py        # Аудит-лог
│   │   └── health.py       # Healthcheck
│   └── middleware.py        # Request logging middleware
├── core/
│   ├── config.py           # Конфигурация (Pydantic Settings)
│   ├── exceptions.py       # Доменные исключения
│   ├── security.py         # AES-256-GCM шифрование
│   ├── logging.py          # Structured logging (structlog)
│   ├── template.py         # Рендер команд с параметрами
│   └── connectors/
│       ├── base.py         # BaseConnector + ConnectorFactory
│       └── ssh.py          # SSH коннектор + фабрика
├── di/
│   └── providers.py        # DI провайдеры (dishka)
├── models/
│   ├── node.py             # Нода
│   ├── command.py          # Шаблон команды
│   ├── script.py           # Скрипт
│   ├── script_execution.py # Результат выполнения скрипта
│   └── audit_log.py        # Аудит-лог
├── repositories/           # Доступ к данным (CRUD)
├── schemas/                # Pydantic-схемы (Request/Response)
└── services/
    ├── node_service.py     # Бизнес-логика нод
    ├── command_service.py  # Бизнес-логика команд
    ├── script_service.py   # Бизнес-логика скриптов
    └── audit_service.py    # Сервис аудит-лога
```

## Лицензия

[MIT](LICENSE)
