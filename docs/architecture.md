# Архитектура

> [README](../README.md) · [API Specification](api-spec.md) · **Architecture** · [Configuration](configuration.md) · [Development](development.md)

## Обзор

Проект использует **layered architecture** с чётким разделением ответственности и строгим направлением зависимостей сверху вниз.

```
API Layer (FastAPI routers + WebSocket)
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

- HTTP endpoints (роутеры), WebSocket endpoints
- Валидация входных данных (Pydantic-схемы)
- Преобразование доменных исключений в HTTP-ответы
- Dependency injection через dishka (`@inject` + `FromDishka`)
- Все роутеры используют `route_class=DishkaRoute`
- Разграничение read/write: `require_write_scope` на мутирующих эндпоинтах

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
- Cursor-based пагинация (keyset pagination)

Не содержит бизнес-логику и не выбрасывает HTTP-исключения.

### Models (`app/models`)

- SQLAlchemy ORM-модели (2.0 стиль: `Mapped[]`, `mapped_column()`)
- Связи, колонки, индексы
- `id` — `Mapped[uuid.UUID]` с `default=uuid.uuid4`
- 6 моделей: Node, Command, Script, ScriptExecution, AuditLog, APIKey

### Schemas (`app/schemas`)

- Pydantic-модели для API (Request / Response)
- Контракты валидации и сериализации
- Включают common-схемы (CursorPage), config, scheduler

### Core (`app/core`)

- Конфигурация (Pydantic Settings) — 18 переменных окружения
- Доменные исключения — 17 классов
- Безопасность (AES-256-GCM, SHA-256 хеширование API ключей)
- Абстрактные интерфейсы (коннекторы, ConnectorFactory)
- Валидация параметров (docker_validation.py)
- Планировщик скриптов (scheduler.py)
- OpenTelemetry телеметрия (telemetry.py)

### Connectors (`app/core/connectors`)

- Взаимодействие с внешними системами (SSH, Docker)
- Каждый наследует `BaseConnector`, реализует `connect()`, `disconnect()`, `execute_command()`
- `execute_command_streaming()` — async generator для WebSocket стриминга
- Поддержка асинхронного контекстного менеджера

---

## Направление зависимостей

```
api             → services, schemas, core (deps, exceptions)
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
| `APP` | Весь жизненный цикл приложения | `Settings`, `async_sessionmaker`, `SSHConnectorFactory`, `ScriptScheduler` |
| `REQUEST` | Один HTTP-запрос / WebSocket | `AsyncSession`, репозитории, сервисы |

### Управление сессией

- `AsyncSession` живёт в скоупе **REQUEST** — новая сессия на каждый запрос
- `expire_on_commit=False` — атрибуты доступны после commit
- Транзакция управляется через `session.begin()` в провайдере
- Репозитории используют `flush()` без `commit()` — транзакция закрывается автоматически
- Провайдеры: `app/di/providers.py`
- Контейнер экспортируется из `app/di/container.py` (для WebSocket и scheduler)

### Провайдеры

| Provider | Поставляет |
|----------|-----------|
| `ConfigProvider` | `Settings` |
| `DbProvider` | `async_sessionmaker`, `AsyncSession` |
| `RepositoryProvider` | Все 7 репозиториев |
| `ConnectorProvider` | `SSHConnectorFactory` |
| `SchedulerProvider` | `ScriptScheduler` |
| `ServiceProvider` | Все 8 сервисов |

---

## Коннекторы

### SSH (`SSHConnector`)

- Key-based и password аутентификация
- `execute_command()` → `(stdout, stderr, exit_code)`
- `execute_command_streaming()` → `AsyncIterator[str]` (для WebSocket)
- Таймаут подключения и выполнения команд
- Аудит-логирование всех SSH-операций

### Docker (`DockerService`)

- Сервис для управления Docker контейнерами на нодах через SSH-коннектор
- `docker_validation.py` — валидация container ID и image name (защита от command injection)
- `shlex.quote()` для безопасного экранирования команд
- Bulk-операции с `asyncio.gather` (параллельное выполнение)

### ConnectorFactory

Паттерн фабрики для создания коннекторов. `ConnectorFactory` (Protocol) в `base.py`, `SSHConnectorFactory` в `ssh.py`. Инжектится через DI (scope=APP), позволяет тестировать сервисы с моками.

---

## Обработка ошибок

Глобальный exception handler в `main.py` маппит доменные исключения в HTTP-статусы:

| Исключения | HTTP |
|------------|------|
| `NodeNotFoundError`, `CommandNotFoundError`, `ScriptNotFoundError`, `TagNotFoundError`, `ContainerNotFoundError`, `ImageNotFoundError` | 404 |
| `APIKeyNotFoundError`, `APIKeyRevokedError`, `APIKeyExpiredError`, `AuthenticationError` | 401 |
| `ConnectionFailedError`, `DockerDaemonError` | 503 |
| `TemplateRenderError`, `DockerValidationError` | 422 |
| `DockerError` | 502 |
| `RequestTimeoutError` | 504 |
| Остальные `DomainError` | 422 |

---

## Структура проекта

```
app/
├── main.py                # FastAPI application, lifespan, exception handler
├── api/
│   ├── deps.py            # Аутентификация (get_current_api_key, require_write_scope)
│   ├── middleware.py       # RequestLogging, Timeout, RateLimit middleware
│   └── v1/
│       ├── nodes.py       # CRUD + SSH + теги + bulk execute + метрики + cursor pagination
│       ├── commands.py    # Шаблоны команд + execute + теги
│       ├── scripts.py     # Пайплайны команд + execute + schedule
│       ├── docker.py      # Docker контейнеры, образы, сети, тома
│       ├── docker_bulk.py # Docker bulk операции
│       ├── audit.py       # Аудит-лог + delete-all
│       ├── api_keys.py    # API ключи CRUD + PATCH
│       ├── config.py      # Экспорт/импорт конфигурации
│       ├── websocket.py   # WebSocket стриминг команд
│       └── health.py      # Healthcheck (liveness + readiness)
├── core/
│   ├── config.py          # Pydantic Settings (18 переменных)
│   ├── exceptions.py      # 17 доменных исключений
│   ├── security.py        # AES-256-GCM + hash_api_key
│   ├── ssh_utils.py       # SSH-утилиты
│   ├── logging.py         # structlog configuration
│   ├── template.py        # Рендер команд с параметрами (shlex.quote)
│   ├── docker_validation.py
│   ├── scheduler.py       # APScheduler wrapper (singleton)
│   ├── telemetry.py       # OpenTelemetry (OTLP)
│   └── connectors/
│       ├── base.py        # BaseConnector + ConnectorFactory + execute_command_streaming
│       └── ssh.py         # SSHConnector + SSHConnectorFactory
├── models/                # 6 SQLAlchemy ORM-моделей
├── schemas/               # Pydantic Request/Response + common + config + scheduler
├── repositories/          # CRUD доступ к данным (+ health repo)
├── services/              # 8 сервисов (+ health, config)
└── di/
    ├── container.py        # Экспорт container для WebSocket/scheduler
    └── providers.py        # dishka провайдеры (6 провайдеров)
```
