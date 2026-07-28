---
title: Тестирование
status: stable
translation_key: development.testing
source_revision: "2026-07-29"
---

# Тестирование

```bash
uv run pytest tests/architecture/ -q
uv run pytest tests/unit/ tests/integration/ tests/integration_ssh/ -q
uv run pytest tests/e2e/ -m docker -q
```

Unit tests мокают внешние SSH и HTTP systems. Integration tests проверяют
границы приложения. Docker-marked E2E tests валидируют полный стек. Для нового
кода нужно покрытие не ниже 80%, для критической логики — не ниже 90%.
