# AGENTS.md — Правила для AI Coding Agents

## [S1] Обзор проекта

**node_nexus_api** — REST API для управления серверными нодами с SSH-подключениями.

### Стек технологий
- Python 3.13+
- FastAPI
- PostgreSQL
- SQLAlchemy 2.0 (async)
- Alembic
- Pydantic v2
- dishka (Dependency Injection)
- asyncssh
- cryptography (AES-256-GCM шифрование)
- fastapi-limiter + pyrate-limiter (rate limiting)
- Valkey (хранилище для rate limiter, совместим с Redis API)
- uv
- ruff
- mypy
- pytest
- pytest-asyncio
- pytest-docker
- structlog
- Conventional Commits

### Основная архитектура
Проект использует layered architecture с чётким разделением ответственности:

```
API Layer (FastAPI routers)
    ↓
Service Layer (бизнес-логика, оркестрация, audit logging)
    ↓
Repository Layer (абстракции доступа к данным)
    ↓
Domain Models / Core / Infrastructure (коннекторы, внешние сервисы)
```

Направление зависимостей **строго сверху вниз**. Внутренние слои ничего не знают о внешних.

---

## [S2] Правила архитектуры и слоёв

### 2.1 Ответственность слоёв

#### API (`app/api`)
- HTTP endpoints (роутеры)
- Валидация входных данных (Pydantic-схемы)
- Преобразование доменных исключений в HTTP-ответы
- Dependency injection (получение сервисов и репозиториев через dishka)
- Rate limiting (через зависимости FastAPI)

**Запрещено:**
- Бизнес-логика (даже простейшая проверка)
- Прямые SQL-запросы или вызовы ORM-сессии
- Прямое обращение к коннекторам и внешним сервисам

#### Services (`app/services`)
- Вся бизнес-логика предметной области
- Оркестрация вызовов репозиториев и внешних коннекторов
- Проверка правил, выдача доменных исключений
- Транзакционность (работа с Unit of Work / сессией при необходимости)
- Audit logging (кросс-функциональная забота)

**Запрещено:**
- Знать детали HTTP (Request, Response)
- Работать с конкретными ORM-моделями (зависимость только от интерфейсов репозиториев или схем)

#### Repositories (`app/repositories`)
- Абстракции для доступа к данным (интерфейсы + реализации на SQLAlchemy)
- CRUD-операции с доменными моделями (но возвращают Pydantic-схемы или чистые объекты данных)
- Работа с `AsyncSession` и построение запросов

**Запрещено:**
- Содержать бизнес-логику
- Выбрасывать HTTP-исключения

#### Domain Models (`app/models`)
- SQLAlchemy ORM-модели
- Связи, колонки, индексы
- Database representation only

**Запрещено:**
- Бизнес-методы, вызовы сервисов, внешние обращения

#### Schemas (`app/schemas`)
- Pydantic-модели для API (Request / Response)
- Контракты валидации и сериализации
- Могут импортировать ORM-модели **только** для настройки `from_attributes = True` и типов аннотаций. Запрещено использовать методы ORM и создавать экземпляры моделей.

#### Core (`app/core`)
- Конфигурация приложения (Settings на Pydantic)
- Базовые доменные исключения
- Абстрактные интерфейсы (коннекторы, шины событий)
- Безопасность (шифрование через cryptography)
- Rate limiting (Valkey/Redis backend через pyrate-limiter)

**Запрещено:**
- Импортировать API, сервисы, репозитории

#### Connectors (`app/core/connectors`)
- Реализация взаимодействия с внешними системами (SSH, Docker, Proxmox и т.д.)
- Каждый коннектор реализует интерфейс, объявленный в `base.py`
- Обязана быть поддержка асинхронного контекстного менеджера (`__aenter__`/`__aexit__`) и корректного закрытия ресурсов

**Запрещено:**
- Импортировать сервисы или репозитории
- Содержать бизнес-правила

### 2.2 Направление зависимостей (разрешённые импорты)

```
api             → services, schemas
services        → repositories, core, connectors (через интерфейсы)
repositories    → models, core
models          → (только SQLAlchemy и стандартные типы)
schemas         → models (разрешено ограниченно)
core            → (ничего из слоёв выше)
connectors      → core (только базовые исключения/интерфейсы)
```

**Явные запреты на импорты:**
- `models` → `services`
- `schemas` → `models` (кроме оговорённого исключения)
- `core` → `api`
- `connectors` → бизнес-логика (`services`, `repositories`)
- Любые циклические зависимости

Если обнаруживается потенциальный цикл — применять Dependency Inversion (вынос интерфейса в `core`).

### 2.3 Добавление новых слоёв
Создавать новый слой (папку) **только** при объективной необходимости, согласованной с архитектором. Сначала попытаться вписать логику в существующую структуру.

---

## [S3] Стандарты Python

### 3.1 Версия языка
Используется Python 3.13+. Весь код должен быть совместим с этой версией.

### 3.2 Type Hints
Обязательны для:
- Всех публичных функций и методов
- Аргументов и возвращаемых значений
- Сложных структур данных (списки, словари с известными типами)

```python
async def get_node(node_id: UUID) -> NodeResponse:
    ...
```

Необязательны для:
- Очевидных локальных переменных (`name = "server"`)
- `self` и `cls`

Использовать:
- `Final` для констант, которые не должны переопределяться
- `TypeAlias` для сложных типов (`UserId: TypeAlias = UUID`)

### 3.3 Naming conventions

| Объект     | Стиль       |
|------------|-------------|
| функции    | snake_case  |
| переменные | snake_case  |
| классы     | PascalCase  |
| константы  | UPPER_CASE  |
| файлы      | snake_case  |

### 3.4 Imports
Порядок импортов (разделяется пустой строкой):
1. Стандартная библиотека
2. Сторонние пакеты
3. Локальные модули приложения

```python
import asyncio
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.node import NodeService
```

Использовать **абсолютные импорты**, начиная от `app`.

### 3.5 Docstrings
Используется Google style.

Обязательны для:
- Публичных классов
- Сервисных методов и репозиториев
- Интерфейсов и абстрактных методов
- Сложной бизнес-логики, требующей пояснений

Минимальный набор секций: `Args`, `Returns`, `Raises`. Для простых свойств/функций docstring не нужен.

---

## [S4] Async правила

Все операции ввода-вывода (БД, сеть, файлы) должны быть асинхронными. Использовать:
- `async` SQLAlchemy (`AsyncSession`)
- `asyncssh`
- `httpx.AsyncClient`

Запрещены блокирующие вызовы:
- `time.sleep()` → `await asyncio.sleep()`
- `requests.get()` → `httpx.AsyncClient.get()`
- Синхронные сессии SQLAlchemy
- `os.path` для удалённых файловых операций (использовать асинхронные библиотеки или `asyncio.to_thread`)

---

## [S5] Обработка ошибок

### 5.1 Иерархия исключений
Все доменные исключения располагаются в `app/core/exceptions.py` и наследуются от базового `DomainError`:

```python
class DomainError(Exception):
    """Базовое исключение предметной области."""

class NodeNotFoundError(DomainError):
    ...

class ConnectionFailedError(DomainError):
    ...
```

### 5.2 Правила обработки
- Никогда не использовать голый `except Exception: pass`.
- При перехвате низкоуровневых исключений обязательно:
  1. Логировать инцидент (structlog)
  2. Сохранять исходную цепочку (`raise NewError(...) from original`)
  3. Преобразовывать в подходящее доменное исключение

```python
try:
    await connector.execute_command(cmd)
except asyncssh.Error as exc:
    raise ConnectionFailedError(f"SSH error on {node.host}") from exc
```

- В API слое должен быть единый exception handler, мапящий доменные ошибки в HTTP-статусы (например, `NodeNotFoundError` → 404, `DomainError` → 422, `ConnectionFailedError` → 503).

---

## [S6] Структура проекта

```
node_nexus_api/
├── app/
│   ├── main.py                # FastAPI application, startup/shutdown
│   ├── api/
│   │   └── v1/
│   │       ├── nodes.py       # CRUD + SSH эндпоинты
│   │       ├── audit.py       # Аудит-лог эндпоинты
│   │       └── health.py      # Healthcheck
│   ├── core/
│   │   ├── config.py          # настройки (Pydantic Settings)
│   │   ├── exceptions.py      # базовые исключения
│   │   ├── security.py        # AES-256-GCM шифрование
│   │   ├── rate_limit.py      # rate limiting (Valkey/Redis backend)
│   │   └── connectors/
│   │       ├── base.py        # интерфейсы коннекторов
│   │       └── ssh.py         # SSH коннектор
│   ├── models/
│   │   ├── base.py            # декларативный базовый класс
│   │   ├── node.py            # модель ноды
│   │   └── audit_log.py       # модель аудит-лога
│   ├── schemas/
│   │   ├── node.py            # Pydantic-схемы нод + PaginatedResponse
│   │   └── audit_log.py       # Pydantic-схемы аудит-лога
│   ├── repositories/
│   │   ├── base.py            # интерфейс базового репозитория
│   │   ├── node_repo.py       # репозиторий нод
│   │   └── audit_repo.py      # репозиторий аудит-лога
│   ├── services/
│   │   ├── node_service.py    # бизнес-логика нод + audit hooks
│   │   └── audit_service.py   # сервис аудит-лога
│   └── di/
│       └── providers.py       # провайдеры dishka
├── tests/
│   ├── unit/                  # unit-тесты (моки, in-memory SQLite)
│   ├── integration/           # integration тесты (SQLite)
│   ├── integration_ssh/       # SSH Docker тесты
│   ├── e2e/                   # E2E тесты (полный стек Docker)
│   └── conftest.py
├── alembic/                   # миграции
├── docker-compose.yml         # development stack
├── docker-compose.e2e.yml     # E2E тест stack
├── Dockerfile
├── pyproject.toml
├── AGENTS.md
└── README.md
```

---

## [S7] Dependency Injection (DI)

### 7.1 Общие правила
- Использовать только **dishka**.
- Запрещено:
  - Создавать экземпляры сервисов/репозиториев вручную через `MyService()`.
  - Хранить состояние в module-level переменных (глобальных синглтонах).
  - Пропускать через DI что-либо, кроме сервисов, репозиториев и объектов конфигурации (контроллеры, роутеры не инжектятся).

### 7.2 Управление сессией
- `AsyncSession` живёт в скоупе **request**. При каждом HTTP-запросе создаётся новая сессия и автоматически закрывается после обработки.
- Провайдеры реализованы в `app/di/providers.py`.

---

## [S8] Работа с базой данных

### 8.1 ORM
- SQLAlchemy 2.0+ (async mode)
- Все запросы выполняются через `AsyncSession`.
- Используются `select()`, `update()`, `delete()` из `sqlalchemy.future`.
- Запрещены:
  - Raw SQL без крайней необходимости.
  - Изменение схемы БД без Alembic-миграции.
  - Синхронные вызовы внутри async-контекста.

### 8.2 Миграции
При изменении ORM-модели необходимо:
1. Изменить модель.
2. Сгенерировать миграцию: `uv run alembic revision --autogenerate -m "description"`.
3. Проверить `upgrade` и `downgrade` на локальной БД.
4. Обновить тестовые fixtures, если изменились поля.

---

## [S9] Репозитории

Репозиторий — единственное место, где происходят SQL-запросы. Сервисы работают с репозиториями, а не с сессией напрямую.

---

## [S10] Коннекторы

### 10.1 Архитектура
Все внешние коннекторы располагаются в `app/core/connectors/`. Каждый коннектор должен:
- Наследоваться от абстрактного базового класса `BaseConnector` (в `base.py`).
- Реализовывать асинхронные методы `connect()`, `disconnect()`.
- Поддерживать контекстный менеджер (`async with connector`).
- Включать встроенные таймауты.
- Выбрасывать только `ConnectionFailedError` или другие доменные исключения.

### 10.2 SSH коннектор
- Поддержка key-based и password аутентификации
- `known_hosts=None` отключает проверку host key (для dev/тестов)
- `execute_command()` возвращает `(stdout, stderr, exit_code)`

---

## [S11] Тестирование

### Инструменты
- pytest, pytest-asyncio, pytest-mock, pytest-docker
- Coverage: pytest-cov

### Структура тестов
```
tests/
├── unit/                  # unit-тесты (моки, in-memory SQLite)
│   ├── test_api_unit.py           # API endpoints с mocked services
│   ├── test_node_service_full.py  # NodeService полное покрытие
│   ├── test_node_service_ssh.py   # SSH логика в сервисе
│   ├── test_node_repo.py          # Repository с in-memory SQLite
│   ├── test_audit_repo.py         # AuditLogRepository
│   ├── test_audit_service.py      # AuditService
│   ├── test_rate_limiting.py      # Rate limiting конфигурация
│   ├── test_rate_limit_core.py    # Rate limit модуль
│   └── test_ssh_connector_unit.py # SSH connector edge cases
├── integration/           # integration тесты (SQLite)
│   └── test_api_integration.py    # Полный CRUD через HTTP
├── integration_ssh/       # SSH Docker тесты
│   └── test_ssh_connector.py      # Реальный SSH сервер
├── e2e/                   # E2E тесты (полный стек)
│   └── test_e2e.py                # PostgreSQL + SSH + API + Valkey
└── conftest.py
```

### Правила
- Все асинхронные тесты помечены `@pytest.mark.asyncio`.
- Внешние системы (SSH, HTTP API) **обязательно** мокать в unit-тестах.
- Интеграционные тесты используют in-memory SQLite.
- E2E тесты запускаются отдельно: `uv run pytest tests/e2e/ -v`

### Coverage
- Текущее покрытие: **91%**
- Минимум для нового кода: 80%
- Критическая бизнес-логика: ≥90%

---

## [S12] Логирование

- Используется `structlog`.
- Уровни:
  - `INFO` — успешные операции
  - `WARNING` — некритичные ошибки
  - `ERROR` — исключения
  - `DEBUG` — детали (только dev)
- **Запрещено логировать**: пароли, токены, приватные ключи

---

## [S13] Конфигурация и переменные окружения

- Все настройки в `app/core/config.py` через Pydantic Settings
- `.env` **не коммитится** в репозиторий

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | URL PostgreSQL | — |
| `SECRET_KEY` | Ключ шифрования | — |
| `REDIS_URL` | URL Valkey/Redis | `redis://localhost:6379/0` |
| `RATE_LIMIT_ENABLED` | Включить rate limiting | `true` |
| `RATE_LIMIT_SSH` | Лимит для SSH | `10/minute` |

---

## [S14] Docker

- Dockerfile: multi-stage, `python:3.13-slim`, пользователь `appuser`
- `docker-compose.yml`: PostgreSQL + Valkey + API
- `docker-compose.e2e.yml`: PostgreSQL + Valkey + SSH + API (для E2E тестов)
- В образ не попадают: `.env`, `.git`, `tests/`, credentials

---

## [S15] Git workflow и коммиты

### Conventional Commits
Формат: `type(scope): краткое описание`

Типы: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`

---

## [S16] Команды разработки

```bash
# Установка
uv sync

# Запуск
uv run python -m app.main

# Тесты
uv run pytest tests/unit/ tests/integration/ -v
uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing

# E2E (требует Docker)
uv run pytest tests/e2e/ -v

# SSH Docker тесты
uv run pytest tests/integration_ssh/ -v

# Линтер
uv run ruff check app/ tests/
uv run ruff format app/ tests/

# Типы
uv run mypy app/

# Миграции
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

---

## [S17] Definition of Done

### Код
- [x] Соответствует слоистой архитектуре
- [x] Type hints для всех публичных функций
- [x] ruff check/format без ошибок
- [x] mypy без ошибок (app/)

### Тесты
- [x] Тесты для новой функциональности
- [x] Все тесты проходят
- [x] Покрытие нового кода ≥80% (критичная логика ≥90%)

### БД
- [x] Alembic-миграция создана и проверена

### Финальная проверка
```bash
uv run ruff check app/ tests/
uv run ruff format --check app/ tests/
uv run mypy app/
uv run pytest tests/unit/ tests/integration/ -q
```

---

Версия документа: 1.2
Дата последнего обновления: 2026-07-10
