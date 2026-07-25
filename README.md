# Node Nexus API

REST API для управления серверными нодами с SSH-подключениями. Централизованное управление инфраструктурой: ноды, SSH-команды, шаблоны, скрипты, Docker-контейнеры — всё через один API.

## Возможности

- **Ноды** — CRUD, фильтрация по тегам, поиск, проверка SSH-связности
- **SSH-команды** — выполнение команд на нодах, bulk-выполнение по ID и тегам
- **Шаблоны команд** — сохранение часто используемых команд с параметрами
- **Скрипты** — пайплайны команд (inline + шаблоны) с поддержкой `on_failure: stop|continue`
- **Docker** — управление контейнерами, образами, сетями и томами на удалённых нодах через SSH
- **Аудит-лог** — запись всех операций с фильтрацией по нодам и типу действия
- **API ключи** — аутентификация через `X-API-Key`, master key, хеширование ключей (SHA-256)
- **Безопасность** — шифрование SSH-ключей и паролей (AES-256-GCM), секреты не возвращаются в ответах

## Быстрый старт

```bash
git clone <repo-url> && cd node_nexus_api

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

[Python](https://www.python.org/) 3.13 · [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 (async) · [Alembic](https://alembic.sqlalchemy.org/) · [Pydantic](https://docs.pydantic.dev/) · [dishka](https://dishka.dev/) · [asyncssh](https://asyncssh.readthedocs.io/) · [cryptography](https://cryptography.io/) · [structlog](https://www.structlog.org/) · [PostgreSQL](https://www.postgresql.org/)

## Документация

- [API спецификация](docs/api-spec.md) — все эндпоинты, схемы, ошибки
- [Архитектура](docs/architecture.md) — слои, структура проекта, DI, коннекторы
- [Конфигурация](docs/configuration.md) — переменные окружения, Docker, аутентификация
- [Разработка](docs/development.md) — workflow, тестирование, команды

## Лицензия

[MIT](LICENSE)
