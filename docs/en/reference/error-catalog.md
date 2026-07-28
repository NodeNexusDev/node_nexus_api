---
title: Error catalog
status: stable
translation_key: reference.error-catalog
source_revision: "2026-07-29"
---

# Error catalog

| Status | Meaning |
|---|---|
| `400` | Malformed or unsupported request |
| `401` | Missing, invalid, expired, or revoked API key |
| `403` | API key lacks write scope |
| `404` | Node, command, script, container, image, or tag not found |
| `409` | Node name conflict |
| `422` | Schema, template, Docker, or domain validation failed |
| `429` | Process-local rate limit exceeded |
| `502` | Remote Docker operation failed |
| `503` | SSH connection or Docker daemon unavailable |
| `504` | Global request timeout |

Domain failures use `{"detail": "message"}`. Do not branch client logic on the
human-readable message; use HTTP status and documented response schemas.
