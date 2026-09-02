---
title: Security model
status: stable
translation_key: architecture.security-model
source_revision: "2026-08-26"
---

# Security model

Node Nexus supports two authentication methods: **API keys** (`X-API-Key`) for
programmatic access and **JWT Bearer tokens** for browser/SPA clients.

**API keys** authenticate clients through `X-API-Key`; scopes authorize read and
write operations. Managed keys are stored as SHA-256 hashes. The master key
configured through `MASTER_API_KEY` always has read-write access.

**JWT tokens** are obtained by POSTing credentials to `/api/v2/auth/login`.
The response contains an access token (short-lived, default 15 minutes) and sets
a refresh token as an `HttpOnly`, `Secure`, `SameSite=Lax` cookie. The access
token is sent as `Authorization: Bearer <token>`. Refresh tokens are rotated on
each use; old tokens are immediately invalidated. JWT is signed with HS256 using
`SECRET_KEY`.

Endpoints that require superuser privileges (`/api/v2/users/*`) check the JWT
`is_superuser` claim. API keys cannot be used for these endpoints — a JWT token
is required.

SSH passwords and private keys are encrypted at rest using a key derived from
`SECRET_KEY` and `ENCRYPTION_SALT`. Production startup requires at least 32
characters for the secret and 16 for the salt. Weaker test credentials are only
accepted when `ENVIRONMENT` is explicitly `development` or `test`. New
ciphertext uses the `enc:v1:` envelope and decryption fails closed; a prefixed or legacy-shaped
ciphertext is never reused as a password after a cryptographic error.

SSH host-key verification is strict by default. Generate `known_hosts` through
a trusted channel, mount it read-only, and set `SSH_KNOWN_HOSTS_PATH`.
`SSH_STRICT_HOST_KEY_CHECKING=false` is reserved for isolated tests.

Non-streaming SSH output is drained through bounded buffers before it reaches
application services. Infrastructure exceptions are exposed through stable
public messages; raw remote stderr is not returned as an HTTP error detail.

Trust boundaries exist at HTTP clients, the database, SSH hosts, Docker daemons,
and telemetry exporters. Validate all boundary input, use parameterized
templates, enforce timeouts, and redact credentials. TLS and network policy are
deployment responsibilities.
