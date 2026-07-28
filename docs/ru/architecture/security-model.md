---
title: Модель безопасности
status: stable
translation_key: architecture.security-model
source_revision: "2026-07-29"
---

# Модель безопасности

API keys аутентифицируют клиентов через `X-API-Key`; scopes авторизуют read и
write operations. Managed keys хранятся как SHA-256 hashes. SSH passwords и
private keys шифруются at rest ключом, производным от `SECRET_KEY` и
`ENCRYPTION_SALT`.

Trust boundaries проходят через HTTP clients, БД, SSH hosts, Docker daemons и
telemetry exporters. Валидируйте boundary input, используйте параметризованные
templates, задавайте timeouts и скрывайте credentials. TLS и network policy —
ответственность deployment.
