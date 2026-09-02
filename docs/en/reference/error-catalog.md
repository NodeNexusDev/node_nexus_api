---
title: Error catalog
status: stable
translation_key: reference.error-catalog
source_revision: "2026-09-02"
---

# Error catalog

| Status | Meaning |
|---|---|
| `207` | Multi-Status — bulk operation partially succeeded (`succeeded>0 && failed>0`) |
| `400` | Malformed or unsupported request |
| `401` | Missing, invalid, expired, or revoked API key |
| `403` | API key lacks write scope |
| `404` | Node, command, script, execution, container, network, volume, image, tag, schedule, favorite, or API key not found |
| `409` | Node name conflict |
| `410` | Gone — removed v1 prefix `/api/v1` (use `/api/v2`) |
| `422` | Schema, template, Docker, schedule, config format, or domain validation failed (including invalid cursor, `M×N>100`, unsupported `format_version`) |
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
- `request_id` — correlation id from the request middleware (`string|null`, `null` if unavailable)
- `detail` — same as `message` for backward compatibility (`Json|null`)

Do not branch client logic on `message` or `detail`; use HTTP status and `code`.

Bulk operations use a `BulkResult<T>` envelope:

```json
{
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "results": [
    {"id": "...", "status": "success"},
    {"id": "...", "status": "error", "error": "..."}
  ]
}
```

Status mapping: `200` all succeeded, `207 Multi-Status` partial
(`succeeded>0 && failed>0`), `422` all failed. `BulkCommandRequestDTO.timeout`
is validated as optional `int` and wired to per-node SSH execution.

## Domain error codes

| Code | HTTP status | Meaning |
|------|-------------|---------|
| `AuthenticationError` | `401` | API key is missing, invalid, or lacks required scope |
| `APIKeyExpiredError` | `401` | API key has expired |
| `APIKeyNotFoundError` | `404` | API key does not exist |
| `APIKeyRevokedError` | `401` | API key has been revoked |
| `AuditWriteError` | `503` | Failed to persist audit record |
| `CommandNotFoundError` | `404` | Command template does not exist |
| `ConnectionFailedError` | `503` | SSH connection failed |
| `ContainerNotFoundError` | `404` | Docker container does not exist |
| `CredentialDecryptionError` | `503` | Failed to decrypt stored credentials |
| `DockerDaemonError` | `503` | Docker daemon is unreachable |
| `DockerError` | `502` | Generic remote Docker operation failed |
| `DockerValidationError` | `422` | Docker request validation failed |
| `ExecutionNotFoundError` | `404` | Execution record does not exist |
| `FavoriteNotFoundError` | `404` | Favorite does not exist |
| `ImageNotFoundError` | `404` | Docker image does not exist |
| `NodeNameConflictError` | `409` | Node name already exists |
| `NodeNotFoundError` | `404` | Node does not exist |
| `NetworkNotFoundError` | `404` | Docker network does not exist |
| `RequestTimeoutError` | `504` | Request exceeded the global timeout |
| `ScheduleNotFoundError` | `404` | Schedule does not exist |
| `SchedulePersistenceError` | `503` | Schedule runtime state update failed |
| `ScheduleValidationError` | `422` | Schedule cron expression or node list is invalid |
| `SchedulerOwnershipError` | `503` | Scheduler could not acquire advisory lock |
| `ScheduledScriptExecutionError` | `422` | Scheduled script execution reported a failed result |
| `ScriptNotFoundError` | `404` | Script does not exist |
| `TagNotFoundError` | `404` | Tag does not exist |
| `TemplateRenderError` | `422` | Command template rendering failed |
| `UnsupportedConfigFormatError` | `422` | Config import format is not supported |
| `VolumeNotFoundError` | `404` | Docker volume does not exist |

Any `DomainError` subclass not listed above maps to `422` by default.
