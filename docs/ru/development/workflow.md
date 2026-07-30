---
title: Workflow разработки
status: stable
translation_key: development.workflow
source_revision: "2026-07-30"
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

## Перед мержем

- [ ] Все тесты проходят: `uv run pytest tests/unit/ tests/integration/ -q`
- [ ] Линтер и форматтер: `uv run ruff check app/ tests/`
- [ ] Проверка типов: `uv run ty check app/`
- [ ] Миграция проверена (если изменились модели)
- [ ] Обе языковые версии обновлены (если изменилось поведение)
- [ ] Сборка MkDocs: `uv run mkdocs build --strict -f mkdocs.en.yml`

Feature-ветки остаются локальными и не пушатся в remote. Только `dev` и `main`
пушатся. Вливайте проверенные ветки в `dev` локально, затем пушьте `dev`. Не
изменяйте `.gitignore` без явного разрешения.
