"""Regenerate the bilingual problem+json error pages from runtime truth.

Slugs are computed with the acronym-aware ``_error_slug`` imported from
``app.api.error_mapping`` -- the same function the API uses to build the
``type`` URI at runtime. This keeps ``APIKeyExpiredError`` documented as
``api-key-expired-error`` (never ``a-p-i-key-expired-error``) and
``HTTP_404`` as ``http-404``. Statuses for mapped domain errors come from
``DOMAIN_ERROR_STATUS``; titles come from :class:`http.HTTPStatus`.

Only the human-readable ``When`` / ``Когда`` phrases live in this script
(keyed by exception class name); everything structural (slugs, type URIs,
statuses, titles, ordering) is derived from runtime mapping output.

Usage:
    python scripts/docs/generate_errors.py           # rewrite both pages
    python scripts/docs/generate_errors.py --check   # fail if pages are stale
"""

from __future__ import annotations

import argparse
import sys
from http import HTTPStatus
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.api.error_mapping import (  # noqa: E402
    DOMAIN_ERROR_STATUS,
    ERROR_TYPE_BASE,
    _error_slug,
)

DOCS_EN = ROOT / "docs" / "en" / "errors.md"
DOCS_RU = ROOT / "docs" / "ru" / "errors.md"

EXTRA_STATUSES: dict[str, int] = {
    "InternalError": 500,
    "RequestValidationError": 422,
}

HTTP_FALLBACK_STATUSES: tuple[int, ...] = (
    400,
    401,
    403,
    404,
    405,
    409,
    410,
    422,
    429,
    500,
    501,
    502,
    503,
    504,
)

WHEN_EN: dict[str, str] = {
    "APIKeyExpiredError": "The API key has expired",
    "APIKeyNotFoundError": "The API key does not exist",
    "APIKeyRevokedError": "The API key has been revoked",
    "AuditReadError": "An audit read or audit-log mapping failed unexpectedly",
    "AuditStatsUnavailableError": "Audit stats cannot be served, capability missing",
    "AuditWriteError": "An obligatory audit event could not be persisted",
    "AuthenticationError": "Authentication failed, credentials missing or invalid",
    "CommandNotFoundError": "The command template does not exist",
    "CommitFailedError": "The request transaction commit failed",
    "ComposeProjectAlreadyExistsError": (
        "A compose project with this name already exists on the node"
    ),
    "ComposeProjectNotFoundError": "The compose project does not exist",
    "ConnectionFailedError": "The remote SSH connection failed",
    "ContainerNotFoundError": "The Docker container does not exist",
    "CredentialDecryptionError": "A stored credential could not be decrypted safely",
    "DockerDaemonError": "The Docker daemon is unreachable",
    "DockerError": "A remote Docker operation failed",
    "DockerValidationError": "Docker request parameters are invalid",
    "DomainError": "Fallback for any other domain failure",
    "ExecutionNotFoundError": "The execution record does not exist",
    "FavoriteNotFoundError": "The favorite does not exist",
    "HostKeyFetchError": "The SSH host key could not be fetched or verified",
    "ImageNotFoundError": "The Docker image does not exist",
    "InsufficientPermissionsError": "The caller lacks the required permission",
    "InternalError": "Unhandled exception fallback, no internals leaked",
    "InvalidCredentialsError": "Login credentials are invalid",
    "InvalidTokenError": "The JWT token is invalid",
    "NetworkNotFoundError": "The Docker network does not exist",
    "NodeNameConflictError": "The node name violates its uniqueness contract",
    "NodeNotFoundError": "The node does not exist",
    "PackConflictError": "The template pack name conflicts",
    "PackNotFoundError": "The template pack does not exist",
    "RegistryConflictError": "The template registry already exists",
    "RegistryNotFoundError": "The template registry does not exist",
    "RequestTimeoutError": "The request exceeded the configured timeout",
    "RequestValidationError": "Request schema validation failed",
    "ScheduleNotFoundError": "The persistent schedule does not exist",
    "SchedulePersistenceError": "Schedule persistence or registration failed",
    "ScheduleValidationError": "Schedule input is invalid",
    "ScheduledScriptExecutionError": (
        "A scheduled script execution reported a failed result"
    ),
    "SchedulerOwnershipError": "This replica does not own scheduler execution",
    "ScriptNotFoundError": "The script does not exist",
    "TagNotFoundError": "The tag does not exist on the node",
    "TemplateRenderError": "The command template cannot be rendered",
    "TokenExpiredError": "The JWT token has expired",
    "UnsupportedConfigFormatError": (
        "The imported configuration format is not supported"
    ),
    "UserAlreadyExistsError": "A user with the given email already exists",
    "UserNotFoundError": "The user does not exist",
    "VolumeNotFoundError": "The Docker volume does not exist",
}

WHEN_SUFFIX_EN: dict[str, str] = {
    "DomainError": " or subclass name",
    "RequestValidationError": (
        ", plus an `errors` array with the raw FastAPI error list"
    ),
}

WHEN_RU: dict[str, str] = {
    "APIKeyExpiredError": "API key истёк",
    "APIKeyNotFoundError": "API key не существует",
    "APIKeyRevokedError": "API key отозван",
    "AuditReadError": "Чтение аудита или маппинг audit-записи неожиданно упал",
    "AuditStatsUnavailableError": (
        "Статистика аудита недоступна, capability отсутствует"
    ),
    "AuditWriteError": "Обязательное audit-событие не удалось сохранить",
    "AuthenticationError": (
        "Аутентификация не удалась, credentials отсутствуют или невалидны"
    ),
    "CommandNotFoundError": "Шаблон команды не существует",
    "CommitFailedError": "Коммит транзакции запроса не удался",
    "ComposeProjectAlreadyExistsError": (
        "Compose-проект с таким именем уже есть на ноде"
    ),
    "ComposeProjectNotFoundError": "Compose-проект не существует",
    "ConnectionFailedError": "Удаленное SSH-соединение не удалось",
    "ContainerNotFoundError": "Docker-контейнер не существует",
    "CredentialDecryptionError": (
        "Сохранённый credential не удалось безопасно расшифровать"
    ),
    "DockerDaemonError": "Docker daemon недоступен",
    "DockerError": "Удалённая Docker-операция не удалась",
    "DockerValidationError": "Параметры Docker-запроса невалидны",
    "DomainError": "Fallback для прочих domain-ошибок",
    "ExecutionNotFoundError": "Запись execution не существует",
    "FavoriteNotFoundError": "Избранное не существует",
    "HostKeyFetchError": "SSH host key не удалось получить или проверить",
    "ImageNotFoundError": "Docker-образ не существует",
    "InsufficientPermissionsError": "Не хватает прав для операции",
    "InternalError": (
        "Fallback необработанных исключений, внутренности не раскрываются"
    ),
    "InvalidCredentialsError": "Неверные credentials для входа",
    "InvalidTokenError": "JWT-токен невалиден",
    "NetworkNotFoundError": "Docker-сеть не существует",
    "NodeNameConflictError": "Имя ноды нарушает контракт уникальности",
    "NodeNotFoundError": "Нода не существует",
    "PackConflictError": "Конфликт имени template pack",
    "PackNotFoundError": "Template pack не существует",
    "RegistryConflictError": "Template registry уже существует",
    "RegistryNotFoundError": "Template registry не существует",
    "RequestTimeoutError": "Запрос превысил настроенный timeout",
    "RequestValidationError": "Ошибка валидации schema запроса",
    "ScheduleNotFoundError": "Persistent schedule не существует",
    "SchedulePersistenceError": "Не удалось сохранить или зарегистрировать schedule",
    "ScheduleValidationError": "Входные данные schedule невалидны",
    "ScheduledScriptExecutionError": (
        "Плановый запуск скрипта завершился с failed-результатом"
    ),
    "SchedulerOwnershipError": "Эта реплика не владеет выполнением scheduler",
    "ScriptNotFoundError": "Скрипт не существует",
    "TagNotFoundError": "Тег отсутствует на ноде",
    "TemplateRenderError": "Шаблон команды не удаётся отрендерить",
    "TokenExpiredError": "JWT-токен истёк",
    "UnsupportedConfigFormatError": (
        "Формат импортируемой конфигурации не поддерживается"
    ),
    "UserAlreadyExistsError": "Пользователь с таким email уже существует",
    "UserNotFoundError": "Пользователь не существует",
    "VolumeNotFoundError": "Docker volume не существует",
}

WHEN_SUFFIX_RU: dict[str, str] = {
    "DomainError": " или имя подкласса",
    "RequestValidationError": (", плюс массив `errors` с сырым списком ошибок FastAPI"),
}

# Rendered from two short literals so no source line exceeds the limit.
_TYPE_ROW_EN = (
    "| `type` | Stable error documentation URI: "
    "`https://nodenexusdev.github.io/node_nexus_api/en/errors/<slug>` |"
)
_TYPE_ROW_RU = (
    "| `type` | Стабильный URI документации ошибки: "
    "`https://nodenexusdev.github.io/node_nexus_api/en/errors/<slug>` |"
)

HEADER_EN = """\
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
__TYPE_ROW__
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

"""

HEADER_RU = """\
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
__TYPE_ROW__
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

"""

REQUEST_VALIDATION_EXTRA_EN = """\
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
"""

REQUEST_VALIDATION_EXTRA_RU = REQUEST_VALIDATION_EXTRA_EN

FOOTER_EN_TITLE = "## HTTP fallback errors"
FOOTER_RU_TITLE = "## HTTP fallback-ошибки"

FOOTER_EN_INTRO = """\
Plain `HTTPException` / Starlette errors keep `code: HTTP_<status>`
with the previous message text as `detail`:"""

FOOTER_RU_INTRO = """\
Обычные `HTTPException` / Starlette-ошибки сохраняют `code: HTTP_<status>`
с прежним текстом message в `detail`:"""


def code_to_status() -> dict[str, int]:
    """Map every documented error code to its runtime HTTP status."""
    mapping: dict[str, int] = {
        exc_cls.__name__: status for exc_cls, status in DOMAIN_ERROR_STATUS.items()
    }
    mapping.update(EXTRA_STATUSES)
    return mapping


def all_codes_sorted() -> list[str]:
    """Return documented codes ordered by their runtime slug."""
    statuses = code_to_status()
    missing = set(statuses) - (set(WHEN_EN) & set(WHEN_RU))
    if missing:
        raise ValueError(f"missing human phrases for: {sorted(missing)}")
    return sorted(statuses, key=_error_slug)


def when_cell(code: str, locale: str) -> str:
    """Build the ``When`` / ``Когда`` table cell for one error code."""
    if locale == "ru":
        phrase = WHEN_RU[code]
        suffix = WHEN_SUFFIX_RU.get(code, "")
    else:
        phrase = WHEN_EN[code]
        suffix = WHEN_SUFFIX_EN.get(code, "")
    return f"{phrase} (`code: {code}`{suffix})"


def error_section(code: str, status: int, locale: str) -> str:
    """Render one per-error section using the runtime slug."""
    slug = _error_slug(code)
    title = HTTPStatus(status).phrase
    header = (
        "| Status | Title | Когда |" if locale == "ru" else "| Status | Title | When |"
    )
    text = (
        f"## {slug}\n"
        "\n"
        f"{header}\n"
        "|---|---|---|\n"
        f"| `{status}` | {title} | {when_cell(code, locale)} |\n"
        "\n"
        f"Type: `{ERROR_TYPE_BASE}/{slug}`\n"
        "\n"
    )
    if code == "RequestValidationError":
        extra = (
            REQUEST_VALIDATION_EXTRA_RU
            if locale == "ru"
            else REQUEST_VALIDATION_EXTRA_EN
        )
        text += extra + "\n"
    return text


def http_footer(locale: str) -> str:
    """Render the HTTP fallback section with runtime-computed suffixes."""
    title = FOOTER_RU_TITLE if locale == "ru" else FOOTER_EN_TITLE
    intro = FOOTER_RU_INTRO if locale == "ru" else FOOTER_EN_INTRO
    header = (
        "| Суффикс `type` | Status | Title |"
        if locale == "ru"
        else "| `type` suffix | Status | Title |"
    )
    lines = [title, "", intro, "", header, "|---|---|---|"]
    for status in HTTP_FALLBACK_STATUSES:
        suffix = _error_slug(f"HTTP_{status}")
        lines.append(f"| `{suffix}` | `{status}` | {HTTPStatus(status).phrase} |")
    lines.append("")
    example_suffix = _error_slug("HTTP_404")
    if locale == "ru":
        lines.append(f"Пример: `{ERROR_TYPE_BASE}/{example_suffix}`")
    else:
        lines.append(f"Example: `{ERROR_TYPE_BASE}/{example_suffix}`")
    lines.append("с `code: HTTP_404`." if locale == "ru" else "with `code: HTTP_404`.")
    lines.append("")
    return "\n".join(lines)


def render(locale: str) -> str:
    """Render the full errors page for one locale."""
    if locale == "ru":
        header = HEADER_RU.replace("__TYPE_ROW__", _TYPE_ROW_RU)
    else:
        header = HEADER_EN.replace("__TYPE_ROW__", _TYPE_ROW_EN)
    statuses = code_to_status()
    parts = [header]
    for code in all_codes_sorted():
        parts.append(error_section(code, statuses[code], locale))
    parts.append(http_footer(locale))
    return "".join(parts)


def main() -> int:
    """Rewrite both error pages, or verify they are current with --check."""
    parser = argparse.ArgumentParser(
        description="Regenerate bilingual error pages from runtime mapping."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail with diff summary instead of writing files",
    )
    args = parser.parse_args()

    rendered = {"en": render("en"), "ru": render("ru")}
    targets = {"en": DOCS_EN, "ru": DOCS_RU}
    if args.check:
        stale = [
            locale
            for locale, path in targets.items()
            if path.read_text(encoding="utf-8") != rendered[locale]
        ]
        if stale:
            print(f"stale error pages: {', '.join(stale)}", file=sys.stderr)
            return 1
        print("error pages are current")
        return 0

    for locale, path in targets.items():
        path.write_text(rendered[locale], encoding="utf-8")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
