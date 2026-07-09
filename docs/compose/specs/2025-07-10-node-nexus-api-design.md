# Node Nexus API - Design Specification

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/node-nexus-api.md)

## [S1] Problem
REST API для управления серверными нодами с различными способами подключения (SSH, Docker, Proxmox).

## [S2] Solution overview
Реализация полной layered architecture с четким разделением ответственности:
- API Layer (FastAPI роутеры)
- Service Layer (бизнес-логика)
- Repository Layer (доступ к данным)
- Domain Models (SQLAlchemy ORM)
- Core (конфигурация, исключения, интерфейсы)
- Connectors (SSH, Docker, Proxmox)

## [S3] Technology stack
- Python 3.13+
- FastAPI
- PostgreSQL 18
- SQLAlchemy 2.0 (async)
- Alembic
- Pydantic v2
- dishka (Dependency Injection)
- asyncssh
- uv
- ruff
- mypy
- pytest
- pytest-asyncio
- structlog

## [S4] Project structure
```
node_nexus_api/
├── app/
│   ├── main.py
│   ├── api/v1/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── services/
│   └── di/
├── tests/
├── alembic/
├── pyproject.toml
└── .env.example
```

## [S5] Data model
Node модель:
- id: UUID (primary key)
- name: str
- host: str
- port: int (default 22)
- connection_type: enum (ssh, docker, proxmox)
- status: enum (active, inactive, error)
- created_at: datetime
- updated_at: datetime

## [S6] API endpoints
- GET /api/v1/nodes - список нод
- GET /api/v1/nodes/{id} - получить ноду
- POST /api/v1/nodes - создать ноду
- PUT /api/v1/nodes/{id} - обновить ноду
- DELETE /api/v1/nodes/{id} - удалить ноду
- GET /health - health check

## [S7] Connectors
SSH коннектор:
- Асинхронный с asyncssh
- Таймауты подключения и выполнения
- Retry логика с exponential backoff
- Контекстный менеджер
- Логирование операций

## [S8] Configuration
Переменные окружения:
- DATABASE_URL
- SECRET_KEY
- DEBUG
- LOG_LEVEL

## [S9] Testing strategy
- Модульные тесты с моками
- Интеграционные тесты с тестовой БД
- E2E тесты с TestClient
- Покрытие: 80% общий, 90% для бизнес-логики

## [S10] Implementation order
1. Базовая инфраструктура (pyproject.toml, структура папок, конфигурация)
2. Модель данных и миграции
3. Репозитории
4. Сервисы
5. API эндпоинты
6. SSH коннектор
7. DI настройка
8. Тесты
9. Docker
10. Документация