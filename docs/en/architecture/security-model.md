---
title: Security model
status: stable
translation_key: architecture.security-model
source_revision: "2026-07-29"
---

# Security model

API keys authenticate clients through `X-API-Key`; scopes authorize read and
write operations. Managed keys are stored as SHA-256 hashes. SSH passwords and
private keys are encrypted at rest using a key derived from `SECRET_KEY` and
`ENCRYPTION_SALT`.

Trust boundaries exist at HTTP clients, the database, SSH hosts, Docker daemons,
and telemetry exporters. Validate all boundary input, use parameterized
templates, enforce timeouts, and redact credentials. TLS and network policy are
deployment responsibilities.
