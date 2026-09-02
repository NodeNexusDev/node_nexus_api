---
title: Testing
status: stable
translation_key: development.testing
source_revision: "2026-09-02"
---

# Testing

Architecture guards plus unit and integration (no Docker):

```bash
uv run pytest tests/architecture/ -q
uv run pytest tests/unit/ tests/integration/ -q
uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing
```

Fast E2E smoke without Docker (uses `openapi.snapshot` cache):

```bash
uv run pytest tests/e2e/ -m "e2e_smoke and not docker" -q
make e2e-fast
```

Full stack E2E (requires Docker):

```bash
uv run pytest tests/e2e/ -m docker -q
make e2e-smoke
```

Coverage guard (docker-free):

```bash
uv run pytest tests/e2e/test_endpoint_coverage_e2e.py -q
make check
```

Unit tests mock external SSH and HTTP systems. Integration tests exercise
application boundaries with in-memory SQLite. Docker-marked E2E tests validate the full stack.
`e2e_smoke` tests are the fast happy-path suite and run without Docker when filtered with `not docker`.

## Coverage

`pyproject.toml [tool.coverage]` uses `branch = true`, `fail_under = 95`, and `omit = ["app/application/ports/*"]`.
Overall project coverage is **95%**. New code needs at least 80% and critical logic at least 90%.
Run with `uv run pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing`.

Unit coverage is split across 5 focused modules: `test_coverage_docker`, `test_coverage_node`, `test_coverage_schemas_docker`, `test_coverage_security`, `test_coverage_services` (replacing the former single `test_coverage_95.py`).

## OpenAPI snapshot cache

`scripts/generate_openapi_snapshot.py` builds the canonical OpenAPI schema via `create_app().openapi()` and writes `scripts/openapi.snapshot.json`.
The snapshot is cached and **gitignored** (see `.gitignore`) — it speeds up the coverage guard without requiring Docker.

Generate manually:

```bash
uv run python scripts/generate_openapi_snapshot.py
make generate-openapi
```

`tests/e2e/test_endpoint_coverage_e2e.py` prefers the cached snapshot if present, otherwise builds the schema directly.

## E2E endpoint coverage guard

`tests/e2e/test_endpoint_coverage_e2e.py` ensures every public HTTP endpoint appears in the coverage manifest.

- `COVERED_ENDPOINTS: set[str]` — endpoints with at least one E2E test.
- `EXCLUDED_ENDPOINTS: dict[str, str]` — justified exclusions (e.g., SSE streaming).
- `COVERED_WS_ENDPOINTS: set[str]` — WebSocket routes not in OpenAPI.

The file `scripts/update_e2e_coverage.py` syncs the manifest from the live OpenAPI inventory:

```bash
uv run python scripts/update_e2e_coverage.py
make update-e2e-coverage
```

It parses `COVERED_ENDPOINTS` / `EXCLUDED_ENDPOINTS` via **AST** (`ast.parse` + `AnnAssign` inspection) with a regex fallback, preserves exclusions, and rewrites only the `COVERED_ENDPOINTS` set. Run this after adding or removing an endpoint, then commit the updated `tests/e2e/test_endpoint_coverage_e2e.py`.

## How to run `make check`

```bash
make check
```

Equivalent to:

```bash
uv run ruff check app/ tests/
uv run ty check .
uv run pytest tests/e2e/test_endpoint_coverage_e2e.py -q
```

Use `make check` before merging to `dev` — it validates lint, types, and that the endpoint manifest is in sync with `openapi.json`.
