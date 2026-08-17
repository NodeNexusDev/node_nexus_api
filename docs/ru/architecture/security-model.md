---
title: Модель безопасности
status: stable
translation_key: architecture.security-model
source_revision: "2026-08-17"
---

# Модель безопасности

API keys аутентифицируют клиентов через `X-API-Key`; scopes авторизуют read и
write operations. Managed keys хранятся как SHA-256 hashes. SSH passwords и
private keys шифруются при хранении ключом, производным от `SECRET_KEY` и
`ENCRYPTION_SALT`. Salt по умолчанию пустой (допустимо для dev/test);
production задаёт его через `.env`. Новый шифротекст использует envelope
`enc:v1:`; ошибка расшифровки обрабатывается с блокировкой доступа, поэтому
шифротекст с префиксом или похожий на устаревший никогда не используется как
пароль после криптографической ошибки.

Проверка SSH host key по умолчанию строгая. Создайте `known_hosts` через
доверенный канал, смонтируйте только для чтения и задайте `SSH_KNOWN_HOSTS_PATH`.
`SSH_STRICT_HOST_KEY_CHECKING=false` допустим только в изолированных тестах.

Границы доверия проходят через HTTP clients, БД, SSH hosts, Docker daemons и
экспортёры телеметрии. Валидируйте входные данные на границах, используйте
параметризованные templates, задавайте timeouts и скрывайте credentials. TLS и
network policy — ответственность развёртывания.
