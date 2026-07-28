---
title: Troubleshooting
status: stable
translation_key: guides.troubleshooting
source_revision: "2026-07-29"
---

# Troubleshooting

- `401`: verify `X-API-Key`, expiry, and revocation state.
- `403`: use a read-write key for mutation.
- `503` on a node: verify DNS, SSH port, credentials, and host-key policy.
- `/ready` fails: check database reachability and migrations.
- scheduled job disappeared: schedules are in-memory and do not survive restart.
- Docker call fails: verify Docker exists and the SSH user has daemon access.

Use the request ID and structured application logs, but never log credentials.
