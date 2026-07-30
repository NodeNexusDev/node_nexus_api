---
title: Security model
status: stable
translation_key: architecture.security-model
source_revision: "2026-07-30"
---

# Security model

API keys authenticate clients through `X-API-Key`; scopes authorize read and
write operations. Managed keys are stored as SHA-256 hashes. SSH passwords and
private keys are encrypted at rest using a key derived from `SECRET_KEY` and
`ENCRYPTION_SALT`. New ciphertext uses the `enc:v1:` envelope and decryption
fails closed; a prefixed or legacy-shaped ciphertext is never reused as a
password after a cryptographic error.

SSH host-key verification is strict by default. Generate `known_hosts` through
a trusted channel, mount it read-only, and set `SSH_KNOWN_HOSTS_PATH`.
`SSH_STRICT_HOST_KEY_CHECKING=false` is reserved for isolated tests.

Trust boundaries exist at HTTP clients, the database, SSH hosts, Docker daemons,
and telemetry exporters. Validate all boundary input, use parameterized
templates, enforce timeouts, and redact credentials. TLS and network policy are
deployment responsibilities.
