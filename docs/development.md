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
├── unit/                  # моки, in-memory SQLite
├── integration/           # SQLite (полный CRUD через HTTP)
├── integration_ssh/       # реальный SSH сервер (Docker)
├── e2e/                   # полный стек (PostgreSQL + SSH + API)
├── helpers.py
└── conftest.py
```

### Команды

```bash
# Unit + integration тесты
uv run pytest tests/unit/ tests/integration/ -v

# С покрытием
uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing

# E2E (требует Docker)
uv run pytest tests/e2e/ -v

# SSH Docker тесты
uv run pytest tests/integration_ssh/ -v
```

### Правила

- Все асинхронные тесты помечены `@pytest.mark.asyncio` (auto mode)
- Внешние системы (SSH, HTTP API) **обязательно** мокать в unit-тестах
- Интеграционные тесты используют in-memory SQLite
- E2E тесты запускаются отдельно

### Coverage

- Текущее покрытие: **91%**
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
```

---

## Команды разработки

```bash
uv sync                       # Установка зависимостей
uv run python -m app.main     # Запуск сервера
uv run pytest ...             # Тесты
uv run ruff check app/ tests/ # Линтер
uv run ruff format app/ tests/# Форматтер
uv run ty check app/          # Типы
```
