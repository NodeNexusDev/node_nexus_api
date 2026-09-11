---
title: Ошибки (problem+json)
status: stable
translation_key: errors
source_revision: "2026-09-11"
---

# Ошибки (`application/problem+json`)

Каждый ответ API с ошибкой использует media type `application/problem+json`
(RFC 9457) с обратно совместимыми полями, поэтому существующие клиенты,
читающие `code` / `message` / `request_id`, продолжают работать.

| Поле | Значение |
|---|---|
| `type` | Стабильный URI документации ошибки: `https://nodenexusdev.github.io/node_nexus_api/en/errors/<slug>` |
| `title` | Стандартная HTTP-фраза для статуса |
| `status` | HTTP-статус (дублирует статус ответа) |
| `detail` | Human-readable описание (текст `message` без изменений) |
| `code` | Machine-readable тип ошибки (имя класса domain exception) |
| `message` | Дубликат `detail` для обратной совместимости |
| `request_id` | Correlation id из request middleware (`string|null`) |
| `instance` | Путь запроса, вызвавшего ошибку |
| `errors` | Только при `422`: сырой список ошибок валидации FastAPI |

Пример payload:

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

Клиентская логика должна ветвиться по HTTP-`status` и `code`, а не по
тексту `message` / `detail`. Внутренние детали неожиданных исключений
никогда не попадают в клиентские поля; они уходят в серверные логи
с корреляцией по `request_id`.

## a-p-i-key-expired-error

| Status | Title | Когда |
|---|---|---|
| `401` | Unauthorized | API key истёк (`code: APIKeyExpiredError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/a-p-i-key-expired-error`

## a-p-i-key-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | API key не существует (`code: APIKeyNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/a-p-i-key-not-found-error`

## a-p-i-key-revoked-error

| Status | Title | Когда |
|---|---|---|
| `401` | Unauthorized | API key отозван (`code: APIKeyRevokedError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/a-p-i-key-revoked-error`

## audit-read-error

| Status | Title | Когда |
|---|---|---|
| `500` | Internal Server Error | Чтение аудита или маппинг audit-записи неожиданно упал (`code: AuditReadError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/audit-read-error`

## audit-stats-unavailable-error

| Status | Title | Когда |
|---|---|---|
| `501` | Not Implemented | Статистика аудита недоступна, capability отсутствует (`code: AuditStatsUnavailableError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/audit-stats-unavailable-error`

## audit-write-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | Обязательное audit-событие не удалось сохранить (`code: AuditWriteError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/audit-write-error`

## authentication-error

| Status | Title | Когда |
|---|---|---|
| `401` | Unauthorized | Аутентификация не удалась, credentials отсутствуют или невалидны (`code: AuthenticationError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/authentication-error`

## command-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Шаблон команды не существует (`code: CommandNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/command-not-found-error`

## commit-failed-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | Коммит транзакции запроса не удался (`code: CommitFailedError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/commit-failed-error`

## compose-project-already-exists-error

| Status | Title | Когда |
|---|---|---|
| `409` | Conflict | Compose-проект с таким именем уже есть на ноде (`code: ComposeProjectAlreadyExistsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/compose-project-already-exists-error`

## compose-project-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Compose-проект не существует (`code: ComposeProjectNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/compose-project-not-found-error`

## connection-failed-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | Удаленное SSH-соединение не удалось (`code: ConnectionFailedError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/connection-failed-error`

## container-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Docker-контейнер не существует (`code: ContainerNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/container-not-found-error`

## credential-decryption-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | Сохранённый credential не удалось безопасно расшифровать (`code: CredentialDecryptionError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/credential-decryption-error`

## docker-daemon-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | Docker daemon недоступен (`code: DockerDaemonError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/docker-daemon-error`

## docker-error

| Status | Title | Когда |
|---|---|---|
| `502` | Bad Gateway | Удалённая Docker-операция не удалась (`code: DockerError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/docker-error`

## docker-validation-error

| Status | Title | Когда |
|---|---|---|
| `422` | Unprocessable Content | Параметры Docker-запроса невалидны (`code: DockerValidationError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/docker-validation-error`

## domain-error

| Status | Title | Когда |
|---|---|---|
| `422` | Unprocessable Content | Fallback для прочих domain-ошибок (`code: DomainError` или имя подкласса) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/domain-error`

## execution-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Запись execution не существует (`code: ExecutionNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/execution-not-found-error`

## favorite-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Избранное не существует (`code: FavoriteNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/favorite-not-found-error`

## host-key-fetch-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | SSH host key не удалось получить или проверить (`code: HostKeyFetchError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/host-key-fetch-error`

## image-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Docker-образ не существует (`code: ImageNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/image-not-found-error`

## insufficient-permissions-error

| Status | Title | Когда |
|---|---|---|
| `403` | Forbidden | Не хватает прав для операции (`code: InsufficientPermissionsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/insufficient-permissions-error`

## internal-error

| Status | Title | Когда |
|---|---|---|
| `500` | Internal Server Error | Fallback необработанных исключений, внутренности не раскрываются (`code: InternalError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/internal-error`

## invalid-credentials-error

| Status | Title | Когда |
|---|---|---|
| `401` | Unauthorized | Неверные credentials для входа (`code: InvalidCredentialsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/invalid-credentials-error`

## invalid-token-error

| Status | Title | Когда |
|---|---|---|
| `401` | Unauthorized | JWT-токен невалиден (`code: InvalidTokenError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/invalid-token-error`

## network-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Docker-сеть не существует (`code: NetworkNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/network-not-found-error`

## node-name-conflict-error

| Status | Title | Когда |
|---|---|---|
| `409` | Conflict | Имя ноды нарушает контракт уникальности (`code: NodeNameConflictError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/node-name-conflict-error`

## node-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Нода не существует (`code: NodeNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/node-not-found-error`

## pack-conflict-error

| Status | Title | Когда |
|---|---|---|
| `409` | Conflict | Конфликт имени template pack (`code: PackConflictError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/pack-conflict-error`

## pack-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Template pack не существует (`code: PackNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/pack-not-found-error`

## request-timeout-error

| Status | Title | Когда |
|---|---|---|
| `504` | Gateway Timeout | Запрос превысил настроенный timeout (`code: RequestTimeoutError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/request-timeout-error`

## request-validation-error

| Status | Title | Когда |
|---|---|---|
| `422` | Unprocessable Content | Ошибка валидации schema запроса (`code: RequestValidationError`, плюс массив `errors` с сырым списком ошибок FastAPI) |

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

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Persistent schedule не существует (`code: ScheduleNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/schedule-not-found-error`

## schedule-persistence-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | Не удалось сохранить или зарегистрировать schedule (`code: SchedulePersistenceError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/schedule-persistence-error`

## schedule-validation-error

| Status | Title | Когда |
|---|---|---|
| `422` | Unprocessable Content | Входные данные schedule невалидны (`code: ScheduleValidationError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/schedule-validation-error`

## scheduled-script-execution-error

| Status | Title | Когда |
|---|---|---|
| `422` | Unprocessable Content | Плановый запуск скрипта завершился с failed-результатом (`code: ScheduledScriptExecutionError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/scheduled-script-execution-error`

## scheduler-ownership-error

| Status | Title | Когда |
|---|---|---|
| `503` | Service Unavailable | Эта реплика не владеет выполнением scheduler (`code: SchedulerOwnershipError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/scheduler-ownership-error`

## script-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Скрипт не существует (`code: ScriptNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/script-not-found-error`

## tag-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Тег отсутствует на ноде (`code: TagNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/tag-not-found-error`

## template-render-error

| Status | Title | Когда |
|---|---|---|
| `422` | Unprocessable Content | Шаблон команды не удаётся отрендерить (`code: TemplateRenderError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/template-render-error`

## token-expired-error

| Status | Title | Когда |
|---|---|---|
| `401` | Unauthorized | JWT-токен истёк (`code: TokenExpiredError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/token-expired-error`

## unsupported-config-format-error

| Status | Title | Когда |
|---|---|---|
| `422` | Unprocessable Content | Формат импортируемой конфигурации не поддерживается (`code: UnsupportedConfigFormatError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/unsupported-config-format-error`

## user-already-exists-error

| Status | Title | Когда |
|---|---|---|
| `409` | Conflict | Пользователь с таким email уже существует (`code: UserAlreadyExistsError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/user-already-exists-error`

## user-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Пользователь не существует (`code: UserNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/user-not-found-error`

## volume-not-found-error

| Status | Title | Когда |
|---|---|---|
| `404` | Not Found | Docker volume не существует (`code: VolumeNotFoundError`) |

Type: `https://nodenexusdev.github.io/node_nexus_api/en/errors/volume-not-found-error`

## HTTP fallback-ошибки

Обычные `HTTPException` / Starlette-ошибки сохраняют `code: HTTP_<status>`
с прежним текстом message в `detail`:

| Суффикс `type` | Status | Title |
|---|---|---|
| `http-400` | `400` | Bad Request |
| `http-401` | `401` | Unauthorized |
| `http-403` | `403` | Forbidden |
| `http-404` | `404` | Not Found |
| `http-405` | `405` | Method Not Allowed |
| `http-409` | `409` | Conflict |
| `http-410` | `410` | Gone |
| `http-422` | `422` | Unprocessable Content |
| `http-429` | `429` | Too Many Requests |
| `http-500` | `500` | Internal Server Error |
| `http-501` | `501` | Not Implemented |
| `http-502` | `502` | Bad Gateway |
| `http-503` | `503` | Service Unavailable |
| `http-504` | `504` | Gateway Timeout |

Пример: `https://nodenexusdev.github.io/node_nexus_api/en/errors/http-404`
с `code: HTTP_404`.
