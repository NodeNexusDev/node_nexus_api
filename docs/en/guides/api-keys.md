---
title: API key lifecycle
status: stable
translation_key: guides.api-keys
source_revision: "2026-07-29"
---

# API key lifecycle

Use the master key only for initial administration and emergency recovery.
Create a managed key for each application or operator so that access can be
scoped, observed, and revoked independently.

## Create and capture a key

Creating a key requires write access:

```bash
curl --fail-with-body -X POST "${NODE_NEXUS_URL}/api/v1/api-keys/" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"name": "inventory-reader", "scope": "read-only"}'
```

The response contains the full `key` exactly once. Transfer it directly to the
consumer's secret store. Later list responses expose only `key_prefix`, which
is suitable for identification but not authentication.

## Set expiration or change scope

List keys with `GET /api/v1/api-keys/?page=1&size=20`, then update one by UUID:

```bash
curl --fail-with-body -X PATCH \
  "${NODE_NEXUS_URL}/api/v1/api-keys/${KEY_ID}" \
  -H "X-API-Key: ${NODE_NEXUS_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"scope": "read-write", "expires_at": "2026-12-31T23:59:59Z"}'
```

Set `is_active` to `false` to disable a key without deleting its record.
Expiration timestamps use ISO 8601. Clients should treat `401` as terminal for
the current credential and must not retry indefinitely.

## Rotate and revoke

Rotate without downtime:

1. Create a replacement key.
2. Store it in the consumer's secret manager.
3. Deploy or reload the consumer and verify successful requests.
4. Disable the old key and monitor for unexpected use.
5. Revoke it with `DELETE /api/v1/api-keys/{key_id}`.

Revocation returns `204 No Content`. Keep the master key outside routine
automation, and never use one shared key for unrelated consumers.
