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
docker-compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Или всё через Docker
docker-compose up -d --build
```

## API

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/v1/nodes/` | Список нод (пагинация: `?page=1&size=20`) |
| `GET` | `/api/v1/nodes/{id}` | Одна нода |
| `POST` | `/api/v1/nodes/` | Создание ноды |
| `PUT` | `/api/v1/nodes/{id}` | Обновление ноды |
| `DELETE` | `/api/v1/nodes/{id}` | Удаление ноды |
| `POST` | `/api/v1/nodes/{id}/check` | Проверка SSH-доступности |
| `POST` | `/api/v1/nodes/{id}/execute` | Выполнение команды через SSH |
| `GET` | `/api/v1/audit/` | Просмотр аудит-лога |
| `GET` | `/health` | Healthcheck |

### Пагинация

```json
GET /api/v1/nodes/?page=1&size=20

{
  "items": [...],
  "total": 150,
  "page": 1,
  "size": 20
}
```

### Выполнение команды

```json
POST /api/v1/nodes/{id}/execute
{ "command": "uptime" }

{
  "stdout": " 12:00:00 up 10 days,  3:45,  1 user,  load average: 0.00, 0.01, 0.05",
  "stderr": "",
  "exit_code": 0
}
```

## Безопасность

- **SSH-ключи и пароли** шифруются AES-256-GCM перед записью в БД
- Секреты **не возвращаются** в API-ответах

## Конфигурация

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | URL PostgreSQL | — |
| `SECRET_KEY` | Ключ шифрования | — |

## Тесты

```bash
# Все тесты
uv run pytest tests/unit/ tests/integration/ -v

# С покрытием
uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing

# E2E (требует Docker)
uv run pytest tests/e2e/ -v
```

**102 теста, покрытие 91%**

| Тип | Кол-во | Описание |
|-----|--------|----------|
| Unit | 70 | Моки, in-memory SQLite |
| Integration | 15 | Реальные SQL-запросы |
| Integration SSH | 6 | Реальный Docker SSH-сервер |
| E2E | 9 | Полный стек (PostgreSQL + SSH + API) |

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

MIT
