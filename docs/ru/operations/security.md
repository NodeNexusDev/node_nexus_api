---
title: Эксплуатационная безопасность
status: stable
translation_key: operations.security
source_revision: "2026-07-30"
---

# Эксплуатационная безопасность

- Создайте независимые случайные `SECRET_KEY` и `MASTER_API_KEY`.
Храните секреты вне images и source control.
- Ограничьте сеть до API, БД и telemetry endpoints.
- Используйте least-privilege SSH users и API key scopes.
- Ротируйте managed keys и отзывайте неиспользуемые.
- Завершайте TLS на доверенном proxy и сохраняйте security headers.
- Проверяйте audit events и dependency scans.

Замена `SECRET_KEY` требует плана повторного шифрования credentials.
