---
title: Quality gates
status: stable
translation_key: development.quality-gates
source_revision: "2026-09-02"
---

# Quality gates

```bash
uv run ruff check app/ tests/ scripts/
uv run ruff format --check app/ tests/ scripts/
uv run ty check .
uv run python scripts/docs/check_docs.py
uv run mkdocs build --strict -f mkdocs.en.yml
uv run mkdocs build --strict -f mkdocs.ru.yml
uv run python scripts/docs/export_openapi.py
uv run python scripts/docs/validate_openapi.py build/openapi.json
uv run python scripts/generate_openapi_snapshot.py
make update-e2e-coverage
```

После статических проверок запустите unit и integration tests:

```bash
uv run pytest tests/architecture/ -q
uv run pytest tests/unit/ tests/integration/ -q
uv run pytest tests/e2e/test_endpoint_coverage_e2e.py -q
make check   # ruff + ty + coverage guard
```

`scripts/openapi.snapshot.json` — кешированный инвентарь OpenAPI для guard'а покрытия (`tests/e2e/test_endpoint_coverage_e2e.py` и `scripts/update_e2e_coverage.py`). Файл **игнорируется в git** (см. `.gitignore`) — сгенерируйте его через `uv run python scripts/generate_openapi_snapshot.py` или `make generate-openapi` перед `make update-e2e-coverage` при изменении endpoints. Guard использует `branch = true`, `fail_under = 95`, `omit = ["app/application/ports/*"]` и падает, если какой-то endpoint отсутствует в `COVERED_ENDPOINTS` / `EXCLUDED_ENDPOINTS`.
