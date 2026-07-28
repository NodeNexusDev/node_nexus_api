# Архитектура

> [README](../README.md) · [API Specification](api-spec.md) · **Architecture** · [Configuration](configuration.md) · [Development](development.md)

## Обзор

Проект — production-oriented **modular monolith**. Границы усиливаются
application DTO/ports и архитектурными тестами; проект не заявляет полную
Clean Architecture.

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

Не знает детали HTTP. CRUD временно может использовать ORM через
request-scoped repository; remote orchestration получает immutable DTO.

### Repositories (`app/repositories`)

- Абстракции для доступа к данным
- CRUD-операции и маппинг ORM в application DTO
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
| `APP` | Весь жизненный цикл приложения | `Settings`, `AsyncEngine`, `async_sessionmaker`, `SSHConnectorFactory`, `ScriptScheduler`, short-scope readers |
| `REQUEST` | Один HTTP-запрос / WebSocket | `AsyncSession`, репозитории, сервисы |

### Управление сессией

- `AsyncEngine` принадлежит **APP** scope и `dispose()` при shutdown
- `AsyncSession` живёт в скоупе **REQUEST** — новая сессия на каждый запрос
- `expire_on_commit=False` — атрибуты доступны после commit
- Транзакция управляется через `session.begin()` в провайдере
- Репозитории используют `flush()` без `commit()` — транзакция закрывается автоматически
- Провайдеры: `app/di/providers.py`
- `ScopedNodeConnectionReader` закрывает короткую session до remote I/O
- WebSocket API не импортирует repositories или глобальный container

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

Единый registry в `app/api/error_mapping.py` маппит доменные исключения в HTTP-статусы:

| Исключения | HTTP |
|------------|------|
| `NodeNotFoundError`, `CommandNotFoundError`, `ScriptNotFoundError`, `TagNotFoundError`, `ContainerNotFoundError`, `ImageNotFoundError` | 404 |
| `NodeNameConflictError` | 409 |
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
│   ├── scheduler.py       # lifecycle-managed APScheduler wrapper
│   ├── telemetry.py       # OpenTelemetry (OTLP)
│   └── connectors/
│       ├── base.py        # BaseConnector + ConnectorFactory + execute_command_streaming
│       └── ssh.py         # SSHConnector + SSHConnectorFactory
├── application/           # immutable DTO, ports, use cases
├── adapters/              # short-scope persistence adapters
├── models/                # 6 SQLAlchemy ORM-моделей
├── schemas/               # Pydantic Request/Response + common + config + scheduler
├── repositories/          # CRUD доступ к данным (+ health repo)
├── services/              # 8 сервисов (+ health, config)
└── di/
    ├── container.py        # application composition root
    └── providers.py        # dishka провайдеры (6 провайдеров)
```

## Транзакционные и runtime lifecycle

```mermaid
sequenceDiagram
    participant API
    participant Reader as Short DB reader
    participant Remote as SSH / Docker
    participant Writer as Short DB writer
    API->>Reader: load immutable DTO
    Reader-->>API: DTO; session closed
    API->>Remote: external I/O
    Remote-->>API: result
    API->>Writer: persist result / audit
```

Bulk следует порядку `preload → gather remote I/O → persist`: один
`AsyncSession` никогда не передаётся concurrent tasks. WebSocket endpoint
обрабатывает wire protocol, а `StreamingCommandService` владеет connector
lifecycle и гарантирует cleanup.

Engine и scheduler создаются APP-scoped generator providers. Их finalizers
освобождают pool и останавливают scheduler при shutdown, включая ошибочный
lifespan. Scheduler однопроцессный и in-memory: jobs теряются после restart,
distributed execution не поддерживается.

Нормативные документы: [overview](architecture/overview.md),
[dependency rules](architecture/dependency-rules.md),
[transaction model](architecture/transaction-model.md),
[runtime lifecycle](architecture/runtime-lifecycle.md) и
[ADR](architecture/decisions/).
