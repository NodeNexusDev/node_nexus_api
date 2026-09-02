---
title: Тестирование
status: stable
translation_key: development.testing
source_revision: "2026-09-02"
---

# Тестирование

Architecture guards плюс unit и integration (без Docker):

```bash
uv run pytest tests/architecture/ -q
uv run pytest tests/unit/ tests/integration/ -q
uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing
```

Быстрый E2E smoke без Docker (использует кеш `openapi.snapshot`):

```bash
uv run pytest tests/e2e/ -m "e2e_smoke and not docker" -q
make e2e-fast
```

Полный стек E2E (требует Docker):

```bash
uv run pytest tests/e2e/ -m docker -q
make e2e-smoke
```

Coverage guard (без Docker):

```bash
uv run pytest tests/e2e/test_endpoint_coverage_e2e.py -q
make check
```

Unit tests мокают внешние SSH и HTTP системы. Integration tests проверяют
границы приложения на in-memory SQLite. Docker-marked E2E tests валидируют полный стек.
Тесты с маркером `e2e_smoke` — быстрый набор happy-path, их можно запускать без Docker через `not docker`.

## Покрытие

В `pyproject.toml [tool.coverage]` задано `branch = true`, `fail_under = 95` и `omit = ["app/application/ports/*"]`.
Общее покрытие проекта — **95%**. Для нового кода нужно не ниже 80%, для критической логики — не ниже 90%.
Запуск: `uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing`.

Unit-покрытие разбито на 5 модулей: `test_coverage_docker`, `test_coverage_node`, `test_coverage_schemas_docker`, `test_coverage_security`, `test_coverage_services` (заменили бывший единый `test_coverage_95.py`).

## Кеш снапшота OpenAPI

`scripts/generate_openapi_snapshot.py` собирает каноническую OpenAPI-схему через `create_app().openapi()` и пишет `scripts/openapi.snapshot.json`.
Снапшот кешируется и **игнорируется в git** (`.gitignore`) — ускоряет проверку покрытия без запуска Docker.

Генерация вручную:

```bash
uv run python scripts/generate_openapi_snapshot.py
make generate-openapi
```

`tests/e2e/test_endpoint_coverage_e2e.py` сначала пробует прочитать кеш, и только если его нет — собирает схему напрямую.

## Guard покрытия E2E endpoints

`tests/e2e/test_endpoint_coverage_e2e.py` гарантирует, что каждый публичный HTTP endpoint учтён в манифесте.

- `COVERED_ENDPOINTS: set[str]` — endpoints, покрытые хотя бы одним E2E тестом.
- `EXCLUDED_ENDPOINTS: dict[str, str]` — обоснованные исключения (например, SSE).
- `COVERED_WS_ENDPOINTS: set[str]` — WebSocket маршруты, которых нет в OpenAPI.

Файл `scripts/update_e2e_coverage.py` синхронизирует манифест с живым OpenAPI:

```bash
uv run python scripts/update_e2e_coverage.py
make update-e2e-coverage
```

Скрипт парсит `COVERED_ENDPOINTS` / `EXCLUDED_ENDPOINTS` через **AST** (`ast.parse` + `AnnAssign`), с fallback на regex, сохраняет исключения и переписывает только `COVERED_ENDPOINTS`. Запускайте его после добавления/удаления endpoint'а и коммитьте обновлённый `tests/e2e/test_endpoint_coverage_e2e.py`.

## Как запустить `make check`

```bash
make check
```

Эквивалент:

```bash
uv run ruff check app/ tests/
uv run ty check .
uv run pytest tests/e2e/test_endpoint_coverage_e2e.py -q
```

Используйте `make check` перед мержем в `dev` — проверка линтера, типов и синхронизации манифеста с `openapi.json`.
