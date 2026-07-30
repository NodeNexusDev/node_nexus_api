---
title: Error catalog
status: stable
translation_key: reference.error-catalog
source_revision: "2026-07-30"
---

# Error catalog

| Status | Meaning |
|---|---|
| `400` | Malformed or unsupported request |
| `401` | Missing, invalid, expired, or revoked API key |
| `403` | API key lacks write scope |
| `404` | Node, command, script, container, image, tag, or schedule not found |
| `409` | Node name conflict |
| `422` | Schema, template, Docker, schedule, config format, or domain validation failed |
| `429` | Process-local rate limit exceeded |
| `502` | Remote Docker operation failed |
| `503` | SSH connection, Docker daemon, credential decryption, audit persistence, or scheduler unavailable |
| `504` | Global request timeout |

Domain failures use a stable JSON envelope:

```json
{
    "code": "NodeNotFoundError",
    "message": "Node ... not found",
    "request_id": "req_abc123",
    "detail": "Node ... not found"
}
```

- `code` — machine-readable error type (the domain exception class name)
- `message` — human-readable description
- `request_id` — correlation id from the request middleware (`null` if unavailable)
- `detail` — same as `message`, for backward compatibility

Do not branch client logic on `message` or `detail`; use HTTP status and `code`.
