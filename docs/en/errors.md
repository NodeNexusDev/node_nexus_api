---
title: Error responses (problem+json)
status: stable
translation_key: errors
source_revision: "2026-09-11"
---

# Error responses (`application/problem+json`)

Every API error response uses the `application/problem+json` media type
(RFC 9457) with legacy-compatible members, so existing clients that read
`code` / `message` / `request_id` keep working.

| Field | Meaning |
|---|---|
| `type` | Stable error documentation URI: `https://nodenexusdev.github.io/node_nexus_api/en/errors/<slug>` |
| `title` | Standard HTTP reason phrase for the status |
| `status` | HTTP status code (duplicates the response status) |
| `detail` | Human-readable description (today's `message` text verbatim) |
| `code` | Machine-readable error type (the domain exception class name) |
| `message` | Duplicate of `detail` for backward compatibility |
| `request_id` | Correlation id from the request middleware (`string|null`) |
| `instance` | Request path that produced the error |
| `errors` | Present only on `422` validation failures: raw FastAPI error list |

Example payload:

```json
{
  "type": "https://nodenexusdev.github.io/node_nexus_api/en/errors/audit-read-error",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Audit log request failed",
  "code": "AuditReadError",
  "message": "Audit log request failed",
  "request_id": "7f3a...",
  "instance": "/api/v2/audit/9f..."
}
```

Client logic should branch on HTTP `status` and `code`, never on
`message` / `detail` text. Unexpected-exception internals are never
rendered into client-facing fields; they go to server logs correlated
by `request_id`.

## a-p-i-key-expired-error

| Status | Title | When |
|---|---|---|
| `401` | Unauthorized | The API key has expired (`code: APIKeyExpiredError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/a-p-i-key-expired-error`

## a-p-i-key-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The API key does not exist (`code: APIKeyNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/a-p-i-key-not-found-error`

## a-p-i-key-revoked-error

| Status | Title | When |
|---|---|---|
| `401` | Unauthorized | The API key has been revoked (`code: APIKeyRevokedError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/a-p-i-key-revoked-error`

## audit-read-error

| Status | Title | When |
|---|---|---|
| `500` | Internal Server Error | An audit read or audit-log mapping failed unexpectedly (`code: AuditReadError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/audit-read-error`

## audit-stats-unavailable-error

| Status | Title | When |
|---|---|---|
| `501` | Not Implemented | Audit stats cannot be served, capability missing (`code: AuditStatsUnavailableError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/audit-stats-unavailable-error`

## audit-write-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | An obligatory audit event could not be persisted (`code: AuditWriteError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/audit-write-error`

## authentication-error

| Status | Title | When |
|---|---|---|
| `401` | Unauthorized | Authentication failed, credentials missing or invalid (`code: AuthenticationError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/authentication-error`

## command-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The command template does not exist (`code: CommandNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/command-not-found-error`

## commit-failed-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | The request transaction commit failed (`code: CommitFailedError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/commit-failed-error`

## compose-project-already-exists-error

| Status | Title | When |
|---|---|---|
| `409` | Conflict | A compose project with this name already exists on the node (`code: ComposeProjectAlreadyExistsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/compose-project-already-exists-error`

## compose-project-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The compose project does not exist (`code: ComposeProjectNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/compose-project-not-found-error`

## connection-failed-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | The remote SSH connection failed (`code: ConnectionFailedError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/connection-failed-error`

## container-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The Docker container does not exist (`code: ContainerNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/container-not-found-error`

## credential-decryption-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | A stored credential could not be decrypted safely (`code: CredentialDecryptionError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/credential-decryption-error`

## docker-daemon-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | The Docker daemon is unreachable (`code: DockerDaemonError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/docker-daemon-error`

## docker-error

| Status | Title | When |
|---|---|---|
| `502` | Bad Gateway | A remote Docker operation failed (`code: DockerError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/docker-error`

## docker-validation-error

| Status | Title | When |
|---|---|---|
| `422` | Unprocessable Content | Docker request parameters are invalid (`code: DockerValidationError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/docker-validation-error`

## domain-error

| Status | Title | When |
|---|---|---|
| `422` | Unprocessable Content | Fallback for any other domain failure (`code: DomainError` or subclass name) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/domain-error`

## execution-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The execution record does not exist (`code: ExecutionNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/execution-not-found-error`

## favorite-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The favorite does not exist (`code: FavoriteNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/favorite-not-found-error`

## host-key-fetch-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | The SSH host key could not be fetched or verified (`code: HostKeyFetchError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/host-key-fetch-error`

## image-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The Docker image does not exist (`code: ImageNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/image-not-found-error`

## insufficient-permissions-error

| Status | Title | When |
|---|---|---|
| `403` | Forbidden | The caller lacks the required permission (`code: InsufficientPermissionsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/insufficient-permissions-error`

## internal-error

| Status | Title | When |
|---|---|---|
| `500` | Internal Server Error | Unhandled exception fallback, no internals leaked (`code: InternalError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/internal-error`

## invalid-credentials-error

| Status | Title | When |
|---|---|---|
| `401` | Unauthorized | Login credentials are invalid (`code: InvalidCredentialsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/invalid-credentials-error`

## invalid-token-error

| Status | Title | When |
|---|---|---|
| `401` | Unauthorized | The JWT token is invalid (`code: InvalidTokenError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/invalid-token-error`

## network-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The Docker network does not exist (`code: NetworkNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/network-not-found-error`

## node-name-conflict-error

| Status | Title | When |
|---|---|---|
| `409` | Conflict | The node name violates its uniqueness contract (`code: NodeNameConflictError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/node-name-conflict-error`

## node-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The node does not exist (`code: NodeNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/node-not-found-error`

## pack-conflict-error

| Status | Title | When |
|---|---|---|
| `409` | Conflict | The template pack name conflicts (`code: PackConflictError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/pack-conflict-error`

## pack-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The template pack does not exist (`code: PackNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/pack-not-found-error`

## request-timeout-error

| Status | Title | When |
|---|---|---|
| `504` | Gateway Timeout | The request exceeded the configured timeout (`code: RequestTimeoutError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/request-timeout-error`

## request-validation-error

| Status | Title | When |
|---|---|---|
| `422` | Unprocessable Content | Request schema validation failed (`code: RequestValidationError`, plus an `errors` array with the raw FastAPI error list) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/request-validation-error`

```json
{
  "type": "https://nodenexusdev.github.io/node_nexus_api/en/errors/request-validation-error",
  "title": "Unprocessable Content",
  "status": 422,
  "detail": "Request validation failed: body.name: Field required",
  "code": "RequestValidationError",
  "message": "Request validation failed: body.name: Field required",
  "request_id": "7f3a...",
  "instance": "/api/v2/nodes",
  "errors": [{"loc": ["body", "name"], "msg": "Field required", "type": "missing"}]
}
```

## schedule-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The persistent schedule does not exist (`code: ScheduleNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/schedule-not-found-error`

## schedule-persistence-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | Schedule persistence or registration failed (`code: SchedulePersistenceError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/schedule-persistence-error`

## schedule-validation-error

| Status | Title | When |
|---|---|---|
| `422` | Unprocessable Content | Schedule input is invalid (`code: ScheduleValidationError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/schedule-validation-error`

## scheduled-script-execution-error

| Status | Title | When |
|---|---|---|
| `422` | Unprocessable Content | A scheduled script execution reported a failed result (`code: ScheduledScriptExecutionError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/scheduled-script-execution-error`

## scheduler-ownership-error

| Status | Title | When |
|---|---|---|
| `503` | Service Unavailable | This replica does not own scheduler execution (`code: SchedulerOwnershipError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/scheduler-ownership-error`

## script-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The script does not exist (`code: ScriptNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/script-not-found-error`

## tag-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The tag does not exist on the node (`code: TagNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/tag-not-found-error`

## template-render-error

| Status | Title | When |
|---|---|---|
| `422` | Unprocessable Content | The command template cannot be rendered (`code: TemplateRenderError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/template-render-error`

## token-expired-error

| Status | Title | When |
|---|---|---|
| `401` | Unauthorized | The JWT token has expired (`code: TokenExpiredError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/token-expired-error`

## unsupported-config-format-error

| Status | Title | When |
|---|---|---|
| `422` | Unprocessable Content | The imported configuration format is not supported (`code: UnsupportedConfigFormatError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/unsupported-config-format-error`

## user-already-exists-error

| Status | Title | When |
|---|---|---|
| `409` | Conflict | A user with the given email already exists (`code: UserAlreadyExistsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/user-already-exists-error`

## user-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The user does not exist (`code: UserNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/user-not-found-error`

## volume-not-found-error

| Status | Title | When |
|---|---|---|
| `404` | Not Found | The Docker volume does not exist (`code: VolumeNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/volume-not-found-error`

## HTTP fallback errors

Plain `HTTPException` / Starlette errors keep `code: HTTP_<status>`
with the previous message text as `detail`:

| `type` suffix | Status | Title |
|---|---|---|
| `h-t-t-p_400` | `400` | Bad Request |
| `h-t-t-p_401` | `401` | Unauthorized |
| `h-t-t-p_403` | `403` | Forbidden |
| `h-t-t-p_404` | `404` | Not Found |
| `h-t-t-p_405` | `405` | Method Not Allowed |
| `h-t-t-p_409` | `409` | Conflict |
| `h-t-t-p_410` | `410` | Gone |
| `h-t-t-p_422` | `422` | Unprocessable Content |
| `h-t-t-p_429` | `429` | Too Many Requests |
| `h-t-t-p_500` | `500` | Internal Server Error |
| `h-t-t-p_501` | `501` | Not Implemented |
| `h-t-t-p_502` | `502` | Bad Gateway |
| `h-t-t-p_503` | `503` | Service Unavailable |
| `h-t-t-p_504` | `504` | Gateway Timeout |

Example: `https://nodenexusdev.github.io/node_nexus_api/en/errors/h-t-t-p_404`
with `code: HTTP_404`.
