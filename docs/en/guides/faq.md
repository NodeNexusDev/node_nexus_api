---
title: FAQ
status: stable
translation_key: guides.faq
source_revision: "2026-07-30"
---

# Frequently asked questions

## How do I add a node?

[Create a node](nodes.md#create-a-node) with SSH credentials, then
[verify connectivity](nodes.md#verify-connectivity). Use the returned UUID
for all subsequent operations.

## How do I run a command on a node?

Two ways:
- **Inline:** `POST /api/v1/nodes/{id}/execute/` with `{"command": "..."}`
- **Template:** [create a command template](commands.md), then `POST
  /api/v1/commands/{id}/execute`

See the [cheat sheet](../reference/cheat-sheet.md) for copy-paste recipes.

## What's the difference between a command and a script?

A **command** is a single SSH execution (inline or parameterized template).
A **script** is an ordered pipeline of multiple command steps with
per-step `stop`/`continue` failure behavior, runnable on multiple nodes.
See [scripts](scripts.md).

## Why do I get 401?

The API key is missing, unknown, inactive, or expired. Check the
`X-API-Key` header and the key's state via `GET /api/v1/api-keys/`.
See [authentication](authentication.md).

## Why do I get 403?

Your key is valid but has `read-only` scope and you attempted a mutation
(POST/PATCH/DELETE). Use a `read-write` key for state-changing operations.
See [API key lifecycle](api-keys.md).

## Why do I get 503?

The SSH connection to the node failed. Check:
- Node host, port, and credentials
- Network reachability from the API server
- SSH host key verification (`SSH_STRICT_HOST_KEY_CHECKING`)
- Docker daemon availability (for Docker operations)

See [troubleshooting](troubleshooting.md).

## How do I use an encrypted SSH key?

Provide the private key in `ssh_key` and the passphrase in `passphrase`
when creating or updating a node. The passphrase is stored encrypted and
passed to the SSH server transparently. Example:

```json
{
  "name": "srv",
  "host": "192.0.2.10",
  "port": 22,
  "connection_type": "ssh",
  "username": "ops",
  "ssh_key": "<private-key>",
  "passphrase": "key-passphrase"
}
```

If the key is not encrypted, omit `passphrase`.

## Why do I get 429?

You exceeded the per-IP rate limit. Wait for the window to reset. The
response includes a `Retry-After` header with the number of seconds to
wait. Default: 100 requests per 60 seconds.
See [authentication](authentication.md#rate-limiting).

## How do I rotate an API key?

[Create a replacement](api-keys.md#create-and-capture-a-key), deploy it to
the consumer, verify, then [disable the old key](api-keys.md#set-expiration-or-change-scope)
and [revoke it](api-keys.md#rotate-and-revoke).

## How do I schedule a script?

Scripts support cron-based [schedules](scripts.md). Create a schedule via
the API with a cron expression, target node IDs, and optional timezone.
Only one replica executes jobs at a time (advisory lock).

## How do I import configuration from another instance?

[Export](../guides/configuration-import-export.md) nodes, commands, and
scripts, then import them into the target instance. Credentials are
excluded from exports and must be re-supplied after import.

## What does "ready" mean?

`GET /ready` checks database connectivity and scheduler reconciliation.
A non-owner replica can be ready (serving HTTP) without executing scheduled
jobs. See [health and readiness](../operations/health-and-readiness.md).

## Where is the full API reference?

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`
- [HTTP API reference](../reference/api.md)
- [Cheat sheet](../reference/cheat-sheet.md)
