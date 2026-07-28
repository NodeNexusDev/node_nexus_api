---
title: Security operations
status: stable
translation_key: operations.security
source_revision: "2026-07-29"
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
