# Node Nexus API

REST API для управления серверными нодами с SSH-подключениями. Централизованное управление инфраструктурой: ноды, SSH-команды, шаблоны, скрипты, Docker-контейнеры — всё через один API.

## Возможности

- **Ноды** — CRUD, фильтрация по тегам, поиск, cursor-based пагинация, проверка SSH-связности
- **Системные метрики** — CPU, RAM, диск, uptime для каждой ноды через SSH
- **SSH-команды** — выполнение команд на нодах с настраиваемым таймаутом, bulk-выполнение по ID и тегам
- **Шаблоны команд** — сохранение часто используемых команд с параметрами и тегами, защита от shell-инъекций
- **Скрипты** — пайплайны команд (inline + шаблоны) с поддержкой `on_failure: stop|continue`, теги, выполнение на нескольких нодах
- **Docker** — управление контейнерами, образами, сетями и томами на удалённых нодах через SSH, bulk-операции
- **Планировщик** — cron-расписание для автоматического выполнения скриптов внутри одного процесса
- **WebSocket** — real-time стриминг вывода команд на ноды
- **Аудит-лог** — запись всех операций с фильтрацией по нодам и типу действия, автоочистка по retention
- **API ключи** — аутентификация через `X-API-Key`, master key, SHA-256 хеширование, scope (read-only/read-write), срок действия
- **Экспорт/импорт** — бэкап и восстановление конфигурации (ноды, команды, скрипты) без секретов
- **Безопасность** — шифрование паролей/SSH-ключей (AES-256-GCM), rate limiting, global request timeout, security headers
- **Observability** — Prometheus `/metrics`, OpenTelemetry tracing, `/health` и `/ready` пробы для Kubernetes

## Быстрый старт

```bash
git clone https://github.com/NodeNexusDev/node_nexus_api.git && cd node_nexus_api

# Настроить окружение
cp .env.example .env

# Запустить (Docker)
docker compose up -d --build
```

Или локально:

```bash
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run python -m app.main
```

## Стек

[Python](https://www.python.org/) 3.13 · [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 (async) · [Alembic](https://alembic.sqlalchemy.org/) · [Pydantic](https://docs.pydantic.dev/) · [dishka](https://dishka.dev/) · [asyncssh](https://asyncssh.readthedocs.io/) · [cryptography](https://cryptography.io/) · [structlog](https://www.structlog.org/) · [PostgreSQL](https://www.postgresql.org/) · [APScheduler](https://apscheduler.readthedocs.io/) · [Prometheus](https://prometheus.io/) · [OpenTelemetry](https://opentelemetry.io/)

## Документация

- [API спецификация](docs/api-spec.md) — все эндпоинты, схемы, ошибки
- [Архитектура](docs/architecture.md) — слои, структура проекта, DI, коннекторы
- [Architecture overview и ADR](docs/architecture/overview.md) — границы, транзакции и lifecycle
- [Конфигурация](docs/configuration.md) — переменные окружения, Docker, аутентификация
- [Разработка](docs/development.md) — workflow, тестирование, команды

Scheduler хранит задания только в памяти процесса: после рестарта расписания
теряются, multi-replica координация не поддерживается.

Полная проверка:

```bash
uv run ruff check app/ tests/
uv run ruff format --check app/ tests/
uv run ty check app/
uv run pytest tests/architecture/ tests/unit/ tests/integration/ tests/integration_ssh/ -q
uv run pytest tests/e2e/ -q
```

## Лицензия

[MIT](LICENSE)
