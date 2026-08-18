---
title: Development workflow
status: stable
translation_key: development.workflow
source_revision: "2026-08-18"
---

# Development workflow

## Branch naming

Create a branch from `dev`:

| Type | Format | Example |
|------|--------|---------|
| Feature | `feature/<description>` | `feature/add-node-tags` |
| Fix | `fix/<issue>-<description>` | `fix/42-ssh-timeout` |
| Refactor | `refactor/<scope>-<what>` | `refactor/persistence-extract-gateway` |
| Docs | `docs/<what>` | `docs/error-catalog-update` |

## Commit format

Use Conventional Commits:

```text
type(scope): short description

type: feat | fix | docs | refactor | test | chore | perf | ci | build
scope: api | core | models | services | repos | connectors | di | tests
```

Examples:

```bash
feat(api): add node connectivity check endpoint
fix(connectors): handle SSH timeout gracefully
docs(reference): update error catalog with schedule errors
refactor(di): extract repository bindings to RepositoryProvider
```

## Pre-commit hooks

Install and run pre-commit hooks before committing:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

The `update-openapi-hash` hook automatically refreshes the OpenAPI contract
snapshot in `tests/unit/test_openapi_contract.py` when the generated schema
changes (for example, after adding an endpoint or bumping the version).

To update the hash manually:

```bash
UPDATE_OPENAPI_HASH=1 uv run pytest tests/unit/test_openapi_contract.py::test_openapi_schema_matches_reviewed_snapshot -q
```

## Before merging

- [ ] All tests pass: `uv run pytest tests/unit/ tests/integration/ -q`
- [ ] Lint and format pass: `uv run ruff check app/ tests/`
- [ ] Types pass: `uv run ty check app/`
- [ ] Migration reviewed (if models changed)
- [ ] Both locale trees updated (if behavior changed)
- [ ] MkDocs builds pass: `uv run mkdocs build --strict -f mkdocs.en.yml`

Feature branches are local and are never pushed to remote. Only `dev` and
`main` are pushed. Merge reviewed branches into `dev` locally, then push `dev`.
Never change `.gitignore` without explicit approval.
