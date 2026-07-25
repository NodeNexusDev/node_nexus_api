# Архитектура

> [README](../README.md) · [API Specification](api-spec.md) · **Architecture** · [Configuration](configuration.md) · [Development](development.md)

## Обзор

Проект использует **layered architecture** с чётким разделением ответственности и строгим направлением зависимостей сверху вниз.

```
API Layer (FastAPI routers)
    ↓
Service Layer (бизнес-логика, оркестрация, audit logging)
    ↓
Repository Layer (абстракции доступа к данным)
    ↓
Domain Models / Core / Infrastructure (коннекторы, внешние сервисы)
```

Внутренние слои ничего не знают о внешних. Нарушение этого правила — архитектурный дефект.

---

## Слои

### API (`app/api`)

- HTTP endpoints (роутеры)
- Валидация входных данных (Pydantic-схемы)
- Преобразование доменных исключений в HTTP-ответы
- Dependency injection через dishka

Не содержит бизнес-логику, прямые SQL-запросы или обращения к коннекторам.

### Services (`app/services`)

- Вся бизнес-логика предметной области
- Оркестрация вызовов репозиториев и внешних коннекторов
- Проверка правил, выдача доменных исключений
- Транзакционность
- Audit logging

Не знает детали HTTP и не работает с ORM-моделями напрямую.

### Repositories (`app/repositories`)

- Абстракции для доступа к данным
- CRUD-операции, возвращают Pydantic-схемы
- Работа с `AsyncSession` и построение запросов

Не содержит бизнес-логику и не выбрасывает HTTP-исключения.

### Models (`app/models`)

- SQLAlchemy ORM-модели (2.0 стиль: `Mapped[]`, `mapped_column()`)
- Связи, колонки, индексы
- `id` — `Mapped[uuid.UUID]` с `default=uuid.uuid4`

### Schemas (`app/schemas`)

- Pydantic-модели для API (Request / Response)
- Контракты валидации и сериализации

### Core (`app/core`)

- Конфигурация (Pydantic Settings)
- Доменные исключения (16 классов)
- Безопасность (AES-256-GCM, хеширование API ключей)
- Абстрактные интерфейсы (коннекторы)
- Валидация параметров (docker_validation.py)

### Connectors (`app/core/connectors`)

- Взаимодействие с внешними системами (SSH, Docker)
- Каждый наследует `BaseConnector`, реализует `connect()`, `disconnect()`, `execute_command()`
- Поддержка асинхронного контекстного менеджера

---

## Направление зависимостей

```
api             → services, schemas
services        → repositories, core, connectors
repositories    → models, core
models          → (только SQLAlchemy)
schemas         → models (ограниченно)
core            → (ничего из слоёв выше)
connectors      → core (базовые исключения/интерфейсы)
```

Запрещены: циклические зависимости, импорт снизу вверх.

---

## Dependency Injection (dishka)

### Scopes

| Scope | Жизненный цикл | Примеры |
|-------|----------------|---------|
| `APP` | Весь жизненный цикл приложения | `Settings`, `async_sessionmaker`, `SSHConnectorFactory` |
| `REQUEST` | Один HTTP-запрос | `AsyncSession`, репозитории, сервисы |

### Управление сессией

- `AsyncSession` живёт в скоупе **REQUEST** — новая сессия на каждый запрос
- `expire_on_commit=False` — атрибуты доступны после commit
- Транзакция управляется через `session.begin()` в провайдере
- Репозитории используют `flush()` без `commit()` — транзакция закрывается автоматически
- Провайдеры: `app/di/providers.py`

---

## Коннекторы

### SSH

- Key-based и password аутентификация
- `known_hosts=None` — отключает проверку host key (dev/тесты)
- `execute_command()` → `(stdout, stderr, exit_code)`
- Аудит-логирование всех SSH-операций

### Docker

- `DockerService` — управление Docker контейнерами на нодах через SSH
- `docker_validation.py` — валидация container ID и image name (защита от command injection)
- Docker команды выполняются через SSH-коннектор на удалённых нодах

### ConnectorFactory

Паттерн фабрики для создания коннекторов. `ConnectorFactory` (Protocol) в `base.py`, `SSHConnectorFactory` в `ssh.py`. Инжектится через DI (scope=APP), позволяет тестировать сервисы с моками.

---

## Обработка ошибок

Глобальный exception handler в `main.py` маппит доменные исключения в HTTP-статусы:

| Исключения | HTTP |
|------------|------|
| `NodeNotFoundError`, `CommandNotFoundError`, `ScriptNotFoundError`, `TagNotFoundError`, `ContainerNotFoundError`, `ImageNotFoundError` | 404 |
| `APIKeyNotFoundError`, `APIKeyRevokedError`, `AuthenticationError` | 401 |
| `ConnectionFailedError`, `DockerDaemonError` | 503 |
| `TemplateRenderError`, `DockerValidationError` | 422 |
| `DockerError` | 502 |
| Остальные `DomainError` | 422 |

---

## Структура проекта

```
app/
├── main.py                # FastAPI application, lifespan, exception handler
├── api/
│   ├── deps.py            # Аутентификация (X-API-Key)
│   ├── middleware.py       # Request logging middleware
│   └── v1/
│       ├── nodes.py       # CRUD + SSH + теги + bulk execute
│       ├── commands.py    # Шаблоны команд + execute
│       ├── scripts.py     # Пайплайны команд + execute
│       ├── docker.py      # Docker контейнеры, образы, сети, тома
│       ├── audit.py       # Аудит-лог
│       ├── api_keys.py    # API ключи
│       └── health.py      # Healthcheck
├── core/
│   ├── config.py          # Pydantic Settings
│   ├── exceptions.py      # 16 доменных исключений
│   ├── security.py        # AES-256-GCM + hash_api_key
│   ├── ssh_utils.py       # SSH-утилиты
│   ├── logging.py         # structlog
│   ├── template.py        # Рендер команд с параметрами
│   ├── docker_validation.py
│   └── connectors/
│       ├── base.py        # BaseConnector + ConnectorFactory
│       └── ssh.py         # SSHConnector + SSHConnectorFactory
├── models/                # SQLAlchemy ORM-модели
├── schemas/               # Pydantic Request/Response
├── repositories/          # CRUD доступ к данным
├── services/              # Бизнес-логика
└── di/
    └── providers.py       # dishka провайдеры
```
