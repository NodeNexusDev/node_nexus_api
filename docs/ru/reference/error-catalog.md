---
title: Каталог ошибок
status: stable
translation_key: reference.error-catalog
source_revision: "2026-08-25"
---

# Каталог ошибок

| Status | Значение |
|---|---|
| `400` | Некорректный или неподдерживаемый request |
| `401` | API key отсутствует, невалиден, истёк или отозван |
| `403` | API key не имеет write scope |
| `404` | Node, command, script, execution, container, network, volume, image, tag, schedule, favorite, note или API key не найден |
| `409` | Конфликт имени ноды |
| `422` | Ошибка schema, template, Docker, schedule, config format или domain validation |
| `429` | Превышен process-local rate limit |
| `502` | Ошибка удалённой Docker operation |
| `503` | Недоступен SSH connection, Docker daemon, credential decryption, audit persistence или scheduler |
| `504` | Global request timeout |

Domain failures используют стабильный JSON-конверт:

```json
{
    "code": "NodeNotFoundError",
    "message": "Node ... not found",
    "request_id": "req_abc123",
    "detail": "Node ... not found"
}
```

- `code` — machine-readable тип ошибки (имя класса domain exception)
- `message` — human-readable описание
- `request_id` — correlation id из request middleware (`null` если недоступен)
- `detail` — то же, что и `message`, для обратной совместимости

Клиентская логика должна опираться на HTTP status и `code`, а не на текст
`message` или `detail`.

## Коды domain-ошибок

| Код | HTTP status | Значение |
|-----|-------------|----------|
| `AuthenticationError` | `401` | API key отсутствует, невалиден или не имеет нужного scope |
| `APIKeyExpiredError` | `401` | API key истёк |
| `APIKeyNotFoundError` | `404` | API key не существует |
| `APIKeyRevokedError` | `401` | API key отозван |
| `AuditWriteError` | `503` | Не удалось записать audit-запись |
| `CommandNotFoundError` | `404` | Шаблон команды не существует |
| `ConnectionFailedError` | `503` | SSH-подключение не удалось |
| `ContainerNotFoundError` | `404` | Docker-контейнер не найден |
| `CredentialDecryptionError` | `503` | Не удалось расшифровать сохранённые учётные данные |
| `DockerDaemonError` | `503` | Docker daemon недоступен |
| `DockerError` | `502` | Общая ошибка удалённой Docker-операции |
| `DockerValidationError` | `422` | Ошибка валидации Docker-запроса |
| `ExecutionNotFoundError` | `404` | Запись выполнения не найдена |
| `FavoriteNotFoundError` | `404` | Избранное не найдено |
| `ImageNotFoundError` | `404` | Docker-образ не найден |
| `NodeNameConflictError` | `409` | Нода с таким именем уже существует |
| `NodeNotFoundError` | `404` | Нода не найдена |
| `NetworkNotFoundError` | `404` | Docker-сеть не найдена |
| `NoteNotFoundError` | `404` | Заметка не найдена |
| `RequestTimeoutError` | `504` | Запрос превысил глобальный timeout |
| `ScheduleNotFoundError` | `404` | Расписание не найдено |
| `SchedulePersistenceError` | `503` | Не удалось обновить runtime-состояние расписания |
| `ScheduleValidationError` | `422` | Невалидное cron-выражение или список нод |
| `SchedulerOwnershipError` | `503` | Планировщик не смог получить advisory lock |
| `ScheduledScriptExecutionError` | `422` | Запланированное выполнение скрипта завершилось с ошибкой |
| `ScriptNotFoundError` | `404` | Скрипт не найден |
| `TagNotFoundError` | `404` | Тег не найден |
| `TemplateRenderError` | `422` | Ошибка рендеринга шаблона команды |
| `UnsupportedConfigFormatError` | `422` | Формат импорта конфигурации не поддерживается |
| `VolumeNotFoundError` | `404` | Docker-volume не найден |

Любой подкласс `DomainError`, не перечисленный выше, по умолчанию маппится на `422`.
