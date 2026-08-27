---
title: Аутентификация
status: stable
translation_key: guides.authentication
source_revision: "2026-08-26"
---

# Аутентификация

Node Nexus поддерживает два метода аутентификации:

- **API keys** (`X-API-Key`) — для программного доступа, CLI и скриптов
- **JWT Bearer tokens** (`Authorization: Bearer`) — для браузерных/SPA-клиентов

Выбор метода зависит от типа клиента. API keys проще для server-to-server
общения. JWT предназначен для интерактивных браузерных сессий, где ротация
refresh tokens и HttpOnly cookies обеспечивают лучшую безопасность.

## Аутентификация по API ключам

Не передавайте ключ в строке запроса: URL часто сохраняются в истории браузера,
журналах доступа и системах мониторинга.

```bash
export NODE_NEXUS_URL=http://localhost:8000
export NODE_NEXUS_API_KEY='replace-with-your-key'

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

Мастер-ключ из `MASTER_API_KEY` всегда имеет права на чтение и запись.
Управляемым ключам можно назначить область `read-only` или `read-write`.
Ключ `read-only` позволяет просматривать ресурсы, но операции изменения
завершаются ответом `403 Forbidden`.

| Статус | Значение | Действие |
|---|---|---|
| `401` | Ключ отсутствует, неизвестен, отключён или просрочен | Проверьте заголовок и состояние ключа |
| `403` | Ключ действителен, но не имеет права на запись | Используйте `read-write` только для изменений |
| `429` | Превышен локальный для процесса лимит запросов | Сделайте паузу до следующего окна |

Храните ключи в менеджере секретов или защищённых переменных окружения. Не
коммитьте и не записывайте их в журналы или задачи. Создание, ротация и отзыв
описаны в [руководстве по API-ключам](api-keys.md).

## JWT аутентификация

JWT auth использует двух-токеновый поток: короткоживущий access token и refresh
token, хранимый в HttpOnly cookie.

### Вход в систему

```bash
curl --fail-with-body \
  -c cookies.txt \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}' \
  "${NODE_NEXUS_URL}/api/v1/auth/login"
```

Ответ:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

Ответ также устанавливает cookie `refresh_token` (`HttpOnly`, `Secure`,
`SameSite=Lax`).

### Использование access token

```bash
curl --fail-with-body \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  "${NODE_NEXUS_URL}/api/v1/auth/me"
```

### Обновление токена

Когда access token истекает, используйте refresh cookie для получения нового.
Refresh token **ротируется** при каждом использовании — старый токен
немедленно инвалидируется.

```bash
curl --fail-with-body \
  -b cookies.txt \
  -c cookies.txt \
  -X POST \
  "${NODE_NEXUS_URL}/api/v1/auth/refresh"
```

### Выход из системы

```bash
curl -b cookies.txt -X POST "${NODE_NEXUS_URL}/api/v1/auth/logout"
```

Очищает cookie refresh token и инвалидирует refresh token на сервере.

### HTTP статусы JWT

| Статус | Значение | Действие |
|---|---|---|
| `401` | Токен отсутствует, истёк или недействителен | Повторите вход для получения нового access token |
| `403` | Токен действителен, но пользователь не суперпользователь | Используйте учётную запись суперпользователя |

## Endpoints только для суперпользователя

Endpoints в `/api/v1/users/` требуют JWT с claim `is_superuser`. API keys
**не могут** быть использованы для этих endpoints — сервер возвращает `401` с
сообщением "Master key cannot be used for user authentication".

Первый суперпользователь создаётся автоматически при startup, если заданы
`INITIAL_SUPERUSER_EMAIL` и `INITIAL_SUPERUSER_PASSWORD`. Все остальные
пользователи создаются через `POST /api/v1/users/` существующим
суперпользователем.

## Приоритет аутентификации

Когда запрос содержит и `X-API-Key`, и `Authorization: Bearer`, security
dependency проверяет в следующем порядке:

1. **Bearer token** — если присутствует, используются JWT claims; невалидный
   токен приводит к fail-closed ответу `401`
2. **API key** — используется только при отсутствии Bearer header

Сервер не скрывает ошибку Bearer token через fallback на второй credential из
того же запроса.

Для endpoints суперпользователя (`/api/v1/users/*`) принимается только JWT.
API keys отклоняются с `401`.

## Ограничение частоты запросов

Запросы ограничены по IP клиента скользящим окном. По умолчанию: 100 запросов
за 60-секундное окно, настраивается через `RATE_LIMIT_REQUESTS` и
`RATE_LIMIT_WINDOW`.

Каждый ответ включает:

| Заголовок | Значение |
|-----------|----------|
| `X-RateLimit-Limit` | Максимум запросов за окно |
| `X-RateLimit-Remaining` | Осталось запросов в текущем окне |

При превышении возвращается `429 Too Many Requests` с:

| Заголовок | Значение |
|-----------|----------|
| `Retry-After` | Секунд до повторной попытки |

Ограничение — **process-local** (в памяти). В multi-replica deployment каждая
реплика ведёт свои счётчики. Пути `/health`, `/ready` и `/metrics` исключены
из ограничения.

Клиентам следует:

- Соблюдать `Retry-After` и не повторять запрос немедленно
- Использовать `X-RateLimit-Remaining` для упреждающего замедления
- По возможности распределять запросы между ключами (лимит per IP, не per key)

## Как работает аутентификация по API ключам

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant AUTH as Security dependency
    participant DB as PostgreSQL
    participant EP as Endpoint

    C->>API: GET /nodes/ + X-API-Key
    API->>AUTH: get_current_api_key(header)

    alt Ключ отсутствует
        AUTH-->>API: 401
        API-->>C: 401 Unauthorized
    else Ключ присутствует
        AUTH->>DB: SELECT key_hash WHERE prefix = ?
        DB-->>AUTH: APIKeyModel | None

        alt Не найден или неактивен
            AUTH-->>API: 401
            API-->>C: 401 Unauthorized
        else Просрочен
            AUTH-->>API: 401
            API-->>C: 401 Unauthorized
        else Действителен
            AUTH-->>API: APIKeyDTO (id, scope)
            API->>EP: вызов endpoint

            alt Write endpoint + read-only ключ
                EP-->>API: 403
                API-->>C: 403 Forbidden
            else Доступ разрешён
                EP-->>API: ответ
                API-->>C: 200 + данные
            end
        end
    end
```

## Как работает JWT аутентификация

```mermaid
sequenceDiagram
    participant C as Client (Browser/SPA)
    participant API as FastAPI
    participant AUTH as AuthService
    participant DB as PostgreSQL
    participant JWT as JWTHandler

    Note over C,JWT: Вход в систему
    C->>API: POST /auth/login {email, password}
    API->>AUTH: login(email, password)
    AUTH->>DB: get_user_id_by_email(email)
    DB-->>AUTH: user_id | None
    AUTH->>AUTH: verify_password(password, hash)
    AUTH->>JWT: encode_access_token(user_id, is_superuser)
    JWT-->>AUTH: access_token
    AUTH->>JWT: encode_refresh_token(user_id)
    JWT-->>AUTH: refresh_token
    AUTH->>DB: save refresh_token_hash
    AUTH-->>API: {access_token, refresh_token}
    API-->>C: 200 + Set-Cookie: refresh_token=...

    Note over C,JWT: Аутентифицированный запрос
    C->>API: GET /auth/me + Bearer token
    API->>JWT: decode_token(token, "access")
    JWT-->>API: user_id, claims
    API->>AUTH: get_current_user(user_id)
    AUTH->>DB: get_user(user_id)
    DB-->>AUTH: UserViewDTO
    API-->>C: 200 + данные пользователя

    Note over C,JWT: Обновление токена (ротация)
    C->>API: POST /auth/refresh + cookie
    API->>JWT: decode_token(refresh_token, "refresh")
    JWT-->>API: user_id
    API->>AUTH: refresh_access_token(hash)
    AUTH->>DB: find_and_invalidate старый refresh token
    AUTH->>JWT: encode_access_token + encode_refresh_token
    AUTH->>DB: save new refresh_token_hash
    AUTH-->>API: {new_access_token, new_refresh_token}
    API-->>C: 200 + Set-Cookie: refresh_token=...
```
