---
title: Workflow разработки
status: stable
translation_key: development.workflow
source_revision: "2026-08-18"
---

# Workflow разработки

## Именование веток

Создавайте ветки от `dev`:

| Тип | Формат | Пример |
|------|--------|--------|
| Feature | `feature/<описание>` | `feature/add-node-tags` |
| Fix | `fix/<issue>-<описание>` | `fix/42-ssh-timeout` |
| Refactor | `refactor/<область>-<что>` | `refactor/persistence-extract-gateway` |
| Docs | `docs/<что>` | `docs/error-catalog-update` |

## Формат коммитов

Используйте Conventional Commits:

```text
type(scope): краткое описание

type: feat | fix | docs | refactor | test | chore | perf | ci | build
scope: api | core | models | services | repos | connectors | di | tests
```

Примеры:

```bash
feat(api): add node connectivity check endpoint
fix(connectors): handle SSH timeout gracefully
docs(reference): update error catalog with schedule errors
refactor(di): extract repository bindings to RepositoryProvider
```

## Pre-commit hooks

Установите и запустите hooks перед коммитом:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

Hook `update-openapi-hash` автоматически обновляет снапшот OpenAPI contract
в `tests/unit/test_openapi_contract.py`, когда сгенерированная схема меняется
(например, после добавления endpoint'а или bump'а версии).

Обновить hash вручную:

```bash
UPDATE_OPENAPI_HASH=1 uv run pytest tests/unit/test_openapi_contract.py::test_openapi_schema_matches_reviewed_snapshot -q
```

## Перед мержем

- [ ] Все тесты проходят: `uv run pytest tests/unit/ tests/integration/ -q`
- [ ] Линтер и форматтер: `uv run ruff check app/ tests/`
- [ ] Строгая проверка типов всего проекта: `uv run ty check .`
- [ ] Миграция проверена (если изменились модели)
- [ ] Обе языковые версии обновлены (если изменилось поведение)
- [ ] Сборка MkDocs: `uv run mkdocs build --strict -f mkdocs.en.yml`

Feature-ветки остаются локальными и не пушатся в remote. Только `dev` и `main`
пушатся. Вливайте проверенные ветки в `dev` локально, затем пушьте `dev`. Не
изменяйте `.gitignore` без явного разрешения.
