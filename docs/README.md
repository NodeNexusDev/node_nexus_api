# Documentation

This directory contains the published documentation for Node Nexus API.

## Structure

- `index.md` — language selection landing page.
- `en/` — English documentation tree.
- `ru/` — Russian documentation tree.
- `landing/` — static landing page for the GitHub Pages root.
- `plans/` — long-term technical plans and roadmaps.

Both locale trees have the same structure:

| Section | Purpose |
|---------|---------|
| `getting-started/` | Installation, configuration, first node |
| `guides/` | Task-oriented user guides |
| `operations/` | Deployment, migrations, observability, security |
| `development/` | Local setup, workflow, testing, adding endpoints |
| `architecture/` | Layer rules, transaction model, runtime lifecycle, ADRs |
| `reference/` | HTTP API, configuration, error catalog, cheat sheet |

## Building locally

```bash
# Validate documentation
uv run python scripts/docs/check_docs.py

# Export OpenAPI artifacts
uv run python scripts/docs/export_openapi.py

# Build both locale sites
uv run mkdocs build --strict -f mkdocs.en.yml
uv run mkdocs build --strict -f mkdocs.ru.yml
```

## Contributing

When behavior changes, update both `docs/en/` and `docs/ru/` in the same change.
English is canonical for identifiers and commands; Russian should be idiomatic
rather than word-for-word. Bump `source_revision` in the front matter of every
changed page.
