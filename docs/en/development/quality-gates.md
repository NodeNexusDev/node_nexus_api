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

Run unit and integration tests after these static checks:

```bash
uv run pytest tests/architecture/ -q
uv run pytest tests/unit/ tests/integration/ -q
uv run pytest tests/e2e/test_endpoint_coverage_e2e.py -q
make check   # ruff + ty + coverage guard
```

`scripts/openapi.snapshot.json` is the cached OpenAPI inventory for the coverage guard (`tests/e2e/test_endpoint_coverage_e2e.py` and `scripts/update_e2e_coverage.py`). It is **gitignored** (see `.gitignore`) — generate it with `uv run python scripts/generate_openapi_snapshot.py` or `make generate-openapi` before running `make update-e2e-coverage` when endpoints change. The guard uses `branch = true`, `fail_under = 95`, `omit = ["app/application/ports/*"]` and fails if any endpoint is missing from `COVERED_ENDPOINTS` / `EXCLUDED_ENDPOINTS`.
