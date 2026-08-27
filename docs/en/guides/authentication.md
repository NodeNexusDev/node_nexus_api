---
title: Authentication
status: stable
translation_key: guides.authentication
source_revision: "2026-08-26"
---

# Authentication

Node Nexus supports two authentication methods:

- **API keys** (`X-API-Key`) — for programmatic access, CLI tools, and scripts
- **JWT Bearer tokens** (`Authorization: Bearer`) — for browser/SPA clients

Which method to use depends on your client type. API keys are simpler for
server-to-server communication. JWT is designed for interactive browser sessions
where refresh token rotation and HttpOnly cookies provide better security.

## API key authentication

Do not put a key in the query string: URLs are commonly retained in browser
history, access logs, and monitoring systems.

```bash
export NODE_NEXUS_URL=http://localhost:8000
export NODE_NEXUS_API_KEY='replace-with-your-key'

curl --fail-with-body \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  "${NODE_NEXUS_URL}/api/v1/nodes/"
```

The master key configured through `MASTER_API_KEY` always has read-write access.
Managed keys support `read-only` and `read-write` scopes. A read-only key can
list and inspect resources but receives `403 Forbidden` for mutations.

| Status | Meaning | Action |
|---|---|---|
| `401` | The key is missing, unknown, inactive, or expired | Check the header and key lifecycle |
| `403` | The key is valid but lacks write scope | Use a read-write key only for mutations |
| `429` | The process-local rate limit was exceeded | Back off and retry after the current window |

Store keys in a secret manager or protected environment variable. Never commit,
log, or paste them into issue trackers. See [API key lifecycle](api-keys.md) for
creation, expiration, rotation, and revocation.

## JWT authentication

JWT auth uses a two-token flow: a short-lived access token and a refresh token
stored as an HttpOnly cookie.

### Login

```bash
curl --fail-with-body \
  -c cookies.txt \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}' \
  "${NODE_NEXUS_URL}/api/v1/auth/login"
```

Response:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

The response also sets a `refresh_token` cookie (`HttpOnly`, `Secure`,
`SameSite=Lax`).

### Using the access token

```bash
curl --fail-with-body \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  "${NODE_NEXUS_URL}/api/v1/auth/me"
```

### Refreshing the token

When the access token expires, use the refresh cookie to get a new one. The
refresh token is **rotated** on each use — the old token is immediately
invalidated.

```bash
curl --fail-with-body \
  -b cookies.txt \
  -c cookies.txt \
  -X POST \
  "${NODE_NEXUS_URL}/api/v1/auth/refresh"
```

### Logout

```bash
curl -b cookies.txt -X POST "${NODE_NEXUS_URL}/api/v1/auth/logout"
```

This clears the refresh token cookie and invalidates the refresh token
server-side.

### JWT status codes

| Status | Meaning | Action |
|---|---|---|
| `401` | Token missing, expired, or invalid | Re-login to obtain a new access token |
| `403` | Token valid but user is not a superuser | Use a superuser account for this endpoint |

## Superuser-only endpoints

Endpoints under `/api/v1/users/` require a JWT with the `is_superuser` claim.
API keys **cannot** be used for these endpoints — the server returns `401` with
the message "Master key cannot be used for user authentication".

The first superuser is created automatically on startup when
`INITIAL_SUPERUSER_EMAIL` and `INITIAL_SUPERUSER_PASSWORD` are set. All other
users are created via `POST /api/v1/users/` by an existing superuser.

## Authentication priority

When a request includes both `X-API-Key` and `Authorization: Bearer`, the
security dependency checks in this order:

1. **Bearer token** — if present, JWT claims are used for authorization; an
   invalid token fails closed with `401`
2. **API key** — used only when the Bearer header is absent

The server never hides an invalid Bearer token by falling back to a second
credential supplied in the same request.

For superuser endpoints (`/api/v1/users/*`), only JWT is accepted. API keys
are rejected with `401`.

## Rate limiting

Requests are rate-limited per client IP using a sliding window. The defaults are
100 requests per 60-second window, configured through `RATE_LIMIT_REQUESTS` and
`RATE_LIMIT_WINDOW`.

Every response includes:

| Header | Meaning |
|--------|---------|
| `X-RateLimit-Limit` | Maximum requests per window |
| `X-RateLimit-Remaining` | Requests remaining in the current window |

When the limit is exceeded, the response is `429 Too Many Requests` with:

| Header | Meaning |
|--------|---------|
| `Retry-After` | Seconds to wait before retrying |

Rate limiting is **process-local** (in-memory). In a multi-replica deployment,
each replica maintains its own counters. The `/health`, `/ready`, and `/metrics`
paths are excluded from rate limiting.

Clients should:

- Honor `Retry-After` and not retry immediately
- Use `X-RateLimit-Remaining` to throttle before hitting the limit
- Distribute requests across keys when possible (limits are per IP, not per key)

## How API key authentication works

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant AUTH as Security dependency
    participant DB as PostgreSQL
    participant EP as Endpoint

    C->>API: GET /nodes/ + X-API-Key
    API->>AUTH: get_current_api_key(header)

    alt Key missing
        AUTH-->>API: 401
        API-->>C: 401 Unauthorized
    else Key present
        AUTH->>DB: SELECT key_hash WHERE prefix = ?
        DB-->>AUTH: APIKeyModel | None

        alt Not found or inactive
            AUTH-->>API: 401
            API-->>C: 401 Unauthorized
        else Expired
            AUTH-->>API: 401
            API-->>C: 401 Unauthorized
        else Valid
            AUTH-->>API: APIKeyDTO (id, scope)
            API->>EP: call endpoint

            alt Write endpoint + read-only key
                EP-->>API: 403
                API-->>C: 403 Forbidden
            else Allowed
                EP-->>API: response
                API-->>C: 200 + data
            end
        end
    end
```

## How JWT authentication works

```mermaid
sequenceDiagram
    participant C as Client (Browser/SPA)
    participant API as FastAPI
    participant AUTH as AuthService
    participant DB as PostgreSQL
    participant JWT as JWTHandler

    Note over C,JWT: Login
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

    Note over C,JWT: Authenticated request
    C->>API: GET /auth/me + Bearer token
    API->>JWT: decode_token(token, "access")
    JWT-->>API: user_id, claims
    API->>AUTH: get_current_user(user_id)
    AUTH->>DB: get_user(user_id)
    DB-->>AUTH: UserViewDTO
    API-->>C: 200 + user data

    Note over C,JWT: Token refresh (rotation)
    C->>API: POST /auth/refresh + cookie
    API->>JWT: decode_token(refresh_token, "refresh")
    JWT-->>API: user_id
    API->>AUTH: refresh_access_token(hash)
    AUTH->>DB: find_and_invalidate old refresh token
    AUTH->>JWT: encode_access_token + encode_refresh_token
    AUTH->>DB: save new refresh_token_hash
    AUTH-->>API: {new_access_token, new_refresh_token}
    API-->>C: 200 + Set-Cookie: refresh_token=...
```
