---
title: User management
status: stable
translation_key: guides.users
source_revision: "2026-09-02"
---

# User management

JWT-based user accounts with superuser scope. Backed by `app/adapters/persistence/user.py` (`SqlAlchemyUserGateway`, `SqlAlchemyRefreshTokenGateway`) and `app/application/services/user_service.py` / `auth_service.py`.

## Authentication

* `POST /api/v2/auth/login` — `{email, password}` → `{access_token, refresh_token}` (`HS256`, `iss=node-nexus-api`, `exp 15m` / `7d`, `jti uuid4`)
* `POST /api/v2/auth/refresh` — `{refresh_token}` → new pair
* `POST /api/v2/auth/logout` — revoke refresh token

Use `Authorization: Bearer <access_token>` for subsequent requests. `X-API-Key` and JWT are interchangeable via `Principal` (`source=jwt|api_key`).

## Endpoints

All `/users` routes require superuser JWT (`require_superuser` → `is_superuser` claim check, else `403`).

### List users

```http
GET /api/v2/users?page=1&size=20
Authorization: Bearer <superuser_token>
```

Response `UserListResponse`:

```json
{
  "items": [
    {"id": "...", "email": "admin@example.com", "is_active": true, "is_superuser": true, "created_at": "..."}
  ],
  "total": 1
}
```

`offset = (page-1)*size`, `limit = size`.

### Create user

```http
POST /api/v2/users
Authorization: Bearer <superuser_token>
Content-Type: application/json

{"email": "dev@example.com", "password": "Secret123!", "is_superuser": false}
```

`201` with `UserResponse`. Password is hashed via `bcrypt.gensalt()` (`PasswordHasherAdapter`). Email validated via `email-validator`.

### Delete user

```http
DELETE /api/v2/users/{user_id}
Authorization: Bearer <superuser_token>
```

`204` on success, `404` if not found.

## Initial superuser

Set via environment:

```bash
INITIAL_SUPERUSER_EMAIL=admin@example.com
INITIAL_SUPERUSER_PASSWORD=Admin12345678  # >=12 chars
```

`ApplicationStartup` creates the user on first boot if `UserReader` finds no existing superuser.

## Example

```bash
## Login
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin12345678"}' | jq .

## List users (superuser)
curl --fail-with-body \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "${NODE_NEXUS_URL}/api/v2/users?page=1&size=20" | jq .

## Create
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v2/users" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"Secret123!","is_superuser":false}'
```

## See also

* `app/api/v2/users.py` — `get_users`, `create_user`, `delete_user`
* `app/api/v2/auth.py` — login/refresh/logout
* `app/adapters/security/jwt_handler.py` — `HS256`, `hash_token` (SHA-256)
* `app/adapters/security/password_hasher.py` — `bcrypt`
