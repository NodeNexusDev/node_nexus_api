---
title: Security operations
status: stable
translation_key: operations.security
source_revision: "2026-07-30"
---

# Security operations

- Generate independent high-entropy `SECRET_KEY` and `MASTER_API_KEY` values.
- Keep secrets outside images and source control.
- Restrict network access to the API, database, and telemetry endpoints.
- Use least-privilege SSH users and API key scopes.
- Rotate managed keys and revoke unused keys.
- Terminate TLS at a trusted proxy and preserve security headers.
- Review audit events and dependency scans.

Changing `SECRET_KEY` requires a credential re-encryption plan.

## Encrypted fields

Node credentials are encrypted at rest with AES-256-GCM using
`SECRET_KEY` + `ENCRYPTION_SALT`:

- `password` — SSH password
- `ssh_key` — SSH private key
- `passphrase` — passphrase for encrypted private keys

These fields are write-only: they are never returned in API responses and
are excluded from configuration exports.
