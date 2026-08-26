---
title: Модель безопасности
status: stable
translation_key: architecture.security-model
source_revision: "2026-08-26"
---

# Модель безопасности

Node Nexus поддерживает два метода аутентификации: **API keys** (`X-API-Key`)
для программного доступа и **JWT Bearer tokens** для браузерных/SPA-клиентов.

**API keys** аутентифицируют клиентов через `X-API-Key`; scopes авторизуют read
и write operations. Managed keys хранятся как SHA-256 hashes. Мастер-ключ из
`MASTER_API_KEY` всегда имеет права на чтение и запись.

**JWT токены** получаются POST-запросом к `/api/v1/auth/login`. Ответ содержит
access token (короткоживущий, по умолчанию 15 минут) и устанавливает refresh
token в `HttpOnly`, `Secure`, `SameSite=Lax` cookie. Access token передаётся как
`Authorization: Bearer <token>`. Refresh tokens ротируются при каждом
использовании; старые токены немедленно инвалидируются. JWT подписывается HS256
с использованием `SECRET_KEY`.

Endpoints, требующие привилегии суперпользователя (`/api/v1/users/*`),
проверяют claim `is_superuser` в JWT. API keys не могут быть использованы для
этих endpoints — необходим JWT токен.

SSH passwords и private keys шифруются при хранении ключом, производным от
`SECRET_KEY` и `ENCRYPTION_SALT`. Salt по умолчанию пустой (допустимо для
dev/test); production задаёт его через `.env`. Новый шифротекст использует
envelope `enc:v1:`; ошибка расшифровки обрабатывается с блокировкой доступа,
поэтому шифротекст с префиксом или похожий на устаревший никогда не используется
как пароль после криптографической ошибки.

Проверка SSH host key по умолчанию строгая. Создайте `known_hosts` через
доверенный канал, смонтируйте только для чтения и задайте `SSH_KNOWN_HOSTS_PATH`.
`SSH_STRICT_HOST_KEY_CHECKING=false` допустим только в изолированных тестах.

Границы доверия проходят через HTTP clients, БД, SSH hosts, Docker daemons и
экспортёры телеметрии. Валидируйте входные данные на границах, используйте
параметризованные templates, задавайте timeouts и скрывайте credentials. TLS и
network policy — ответственность развёртывания.
