---
title: Quality gates
status: stable
translation_key: development.quality-gates
source_revision: "2026-07-29"
---

# Quality gates

```bash
uv run ruff check app/ tests/ scripts/
uv run ruff format --check app/ tests/ scripts/
uv run ty check app/
uv run python scripts/docs/check_docs.py
uv run mkdocs build --strict -f mkdocs.en.yml
uv run mkdocs build --strict -f mkdocs.ru.yml
uv run python scripts/docs/export_openapi.py
uv run python scripts/docs/validate_openapi.py build/openapi.json
```

После статических проверок запустите unit и integration tests.
