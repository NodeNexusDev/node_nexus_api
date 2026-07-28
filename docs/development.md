# Разработка

> [README](../README.md) · [API Specification](api-spec.md) · [Architecture](architecture.md) · [Configuration](configuration.md) · **Development**

## Workflow

### Branch-based процесс

```
1. Описать задачу
2. Создать ветку feature/xxx от dev (локально)
3. Внести изменения + коммитить
4. Review результата
5. Мерж в dev (локально)
6. Пуш dev в remote
```

Feature ветки **не пушатся** в remote. Только `dev` и `main` пушатся.

### Нейминг веток

| Тип | Формат | Пример |
|-----|--------|--------|
| Feature | `feature/<short-description>` | `feature/add-node-service` |
| Fix | `fix/<issue-number>-<short>` | `fix/42-ssh-timeout` |
| Refactor | `refactor/<scope>-<what>` | `refactor/repo-base-class` |
| Docs | `docs/<what>` | `docs/api-examples` |

### Формат коммитов (Conventional Commits)

```
type(scope): краткое описание

type: feat | fix | docs | refactor | test | chore | perf | ci | build
scope: api | core | models | services | repos | connectors | di | tests | templates
```

Примеры:
```
feat(services): add NodeService CRUD methods
fix(connectors): handle SSH timeout error
docs(api): add endpoint examples
test(services): add unit tests for NodeService
```

---

## Тестирование

### Структура

```
tests/
├── architecture/          # исполняемые dependency contracts
├── unit/                  # моки, in-memory SQLite
├── integration/           # SQLite (полный CRUD через HTTP)
├── integration_ssh/       # реальный SSH сервер (Docker)
├── e2e/                   # полный стек (PostgreSQL + SSH + API)
├── helpers.py
└── conftest.py
```

### Команды

```bash
# Unit + integration тесты (быстро, без Docker)
uv run pytest tests/unit/ tests/integration/ -v

# Архитектурные контракты (запускаются в CI первыми)
uv run pytest tests/architecture/ -q

# С покрытием
uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing

# Конкретный файл
uv run pytest tests/unit/test_node_metrics.py -v

# E2E (требует Docker; marker исключён в pytest defaults)
uv run pytest tests/e2e/ -m docker -v

# SSH Docker тесты
uv run pytest tests/integration_ssh/ -v
```

### Правила

- Все асинхронные тесты помечены `@pytest.mark.asyncio` (auto mode)
- Внешние системы (SSH, HTTP API) **обязательно** мокать в unit-тестах
- Интеграционные тесты используют in-memory SQLite
- E2E тесты запускаются отдельно
- Для тестов `@inject`-эндпоинтов через `ASGITransport` — использовать `__dishka_orig_func__` для bypass декоратора

### Coverage

- Количество тестов не фиксируется в документации: актуальное значение сообщает pytest
- Минимум для нового кода: **80%**
- Критическая бизнес-логика: **≥90%**

---

## Проверки качества

```bash
# Линтер
uv run ruff check app/ tests/

# Форматтер
uv run ruff format --check app/ tests/

# Типы
uv run ty check app/
```

Или все сразу через `/validate`.

---

## Миграции

```bash
# Сгенерировать миграцию
uv run alembic revision --autogenerate -m "описание"

# Применить
uv run alembic upgrade head

# Откатить одну
uv run alembic downgrade -1

# Показать историю
uv run alembic history
```

Перед merge проверить `upgrade` и `downgrade`. Миграция unique index для
`nodes.name` намеренно завершится ошибкой при существующих дублях: сначала их
должен однозначно исправить оператор.

---

## Команды разработки

```bash
uv sync                       # Установка зависимостей
uv run python -m app.main     # Запуск сервера
uv run pytest ...             # Тесты
uv run ruff check app/ tests/ # Линтер
uv run ruff format app/ tests/# Форматтер
uv run ty check app/          # Типы
uv run alembic upgrade head   # Миграции
```

---

## CI/CD

### GitHub Actions

- **CI** (`.github/workflows/ci.yml`): lint → architecture contracts → test → docker build → security scan

## Persistence scope

- Короткий CRUD использует request-scoped repository.
- SSH/Docker/WebSocket: short reader → immutable DTO → закрытая session →
  remote I/O → short writer.
- Один `AsyncSession` запрещено передавать в `asyncio.gather`.
- Script execution использует short definition/command/node readers и
  отдельный execution writer для каждого state transition.
- Docker facade остаётся тонким; use case добавляется в соответствующий модуль
  `app/services/docker/`, а не непосредственно в facade.
- Новый архитектурный компромисс оформляется ADR в
  `docs/architecture/decisions/`.
- **Release** (`.github/workflows/release.yml`): build Docker image + create GitHub Release при пуше тега

### Pre-commit хуки

- `ruff` (lint + format)
- `trailing-whitespace`, `end-of-file-fixer`
- `check-yaml`, `check-added-large-files`, `check-merge-conflict`
- `debug-statements`
- `commitizen` (проверка формата коммитов)
