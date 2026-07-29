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
`ENCRYPTION_SALT`. Новый ciphertext использует envelope `enc:v1:`; ошибка
расшифровки обрабатывается fail closed, поэтому prefixed или похожий на legacy
ciphertext никогда не используется как пароль после cryptographic error.

Проверка SSH host key по умолчанию строгая. Создайте `known_hosts` через
доверенный канал, смонтируйте read-only и задайте `SSH_KNOWN_HOSTS_PATH`.
`SSH_STRICT_HOST_KEY_CHECKING=false` допустим только в изолированных тестах.

Trust boundaries проходят через HTTP clients, БД, SSH hosts, Docker daemons и
telemetry exporters. Валидируйте boundary input, используйте параметризованные
templates, задавайте timeouts и скрывайте credentials. TLS и network policy —
ответственность deployment.
