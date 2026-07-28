---
title: Testing
status: stable
translation_key: development.testing
source_revision: "2026-07-29"
---

# Testing

```bash
uv run pytest tests/architecture/ -q
uv run pytest tests/unit/ tests/integration/ tests/integration_ssh/ -q
uv run pytest tests/e2e/ -m docker -q
```

Unit tests mock external SSH and HTTP systems. Integration tests exercise
application boundaries. Docker-marked E2E tests validate the full stack.
New code needs at least 80% coverage and critical logic at least 90%.
