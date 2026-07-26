# API Specification

> [README](../README.md) · **API Specification** · [Architecture](architecture.md) · [Configuration](configuration.md) · [Development](development.md)

Версия API: **v1**
Base URL: `/api/v1`

---

## Содержание

### Ресурсы

| Ресурс | Описание |
|--------|----------|
| [Аутентификация](#аутентификация) | API Key аутентификация |
| [Nodes](#nodes) | CRUD ноды, проверка доступности, SSH-команды, метрики |
| [Audit](#audit) | Аудит-лог операций, очистка |
| [Commands](#commands) | Шаблоны команд с параметрами и тегами |
| [Scripts](#scripts) | Пайплайны команд (скрипты), планировщик |
| [API Keys](#api-keys) | Управление API ключами (scope, expiry) |
| [Docker](#docker) | Управление Docker контейнерами на нодах + bulk |
| [Config](#config) | Экспорт/импорт конфигурации |
| [WebSocket](#websocket) | Стриминг вывода команд |
| [Health](#health) | Healthcheck (liveness + readiness) |

### Nodes

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | [`/api/v1/nodes/`](#get-apiv1nodes) | Список нод (фильтрация, поиск) |
| GET | [`/api/v1/nodes/tags`](#get-apiv1nodestags) | Все уникальные теги |
| GET | [`/api/v1/nodes/{node_id}`](#get-apiv1nodesnode_id) | Нода по ID |
| POST | [`/api/v1/nodes/`](#post-apiv1nodes) | Создать ноду |
| PUT | [`/api/v1/nodes/{node_id}`](#put-apiv1nodesnode_id) | Обновить ноду |
| DELETE | [`/api/v1/nodes/{node_id}`](#delete-apiv1nodesnode_id) | Удалить ноду |
| POST | [`/api/v1/nodes/bulk/execute`](#post-apiv1nodesbulkexecute) | Bulk-выполнение команд |
| POST | [`/api/v1/nodes/{node_id}/check`](#post-apiv1nodesnode_idcheck) | Проверить SSH |
| POST | [`/api/v1/nodes/{node_id}/execute`](#post-apiv1nodesnode_idexecute) | Выполнить команду |
| GET | [`/api/v1/nodes/{node_id}/metrics`](#get-apiv1nodesnode_idmetrics) | Системные метрики |
| POST | [`/api/v1/nodes/{node_id}/tags`](#post-apiv1nodesnode_idtags) | Добавить тег |
| DELETE | [`/api/v1/nodes/{node_id}/tags`](#delete-apiv1nodesnode_idtags) | Удалить тег |

### Commands

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | [`/api/v1/commands/`](#get-apiv1commands) | Список команд |
| GET | [`/api/v1/commands/{command_id}`](#get-apiv1commandscommand_id) | Команда по ID |
| POST | [`/api/v1/commands/`](#post-apiv1commands) | Создать команду |
| PUT | [`/api/v1/commands/{command_id}`](#put-apiv1commandscommand_id) | Обновить команду |
| DELETE | [`/api/v1/commands/{command_id}`](#delete-apiv1commandscommand_id) | Удалить команду |
| POST | [`/api/v1/commands/{command_id}/execute`](#post-apiv1commandscommand_idexecute) | Выполнить на ноде |

### Scripts

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | [`/api/v1/scripts/`](#get-apiv1scripts) | Список скриптов (с фильтрацией по тегам) |
| GET | [`/api/v1/scripts/{script_id}`](#get-apiv1scriptsscript_id) | Скрипт по ID |
| POST | [`/api/v1/scripts/`](#post-apiv1scripts) | Создать скрипт |
| PUT | [`/api/v1/scripts/{script_id}`](#put-apiv1scriptsscript_id) | Обновить скрипт |
| DELETE | [`/api/v1/scripts/{script_id}`](#delete-apiv1scriptsscript_id) | Удалить скрипт |
| POST | [`/api/v1/scripts/{script_id}/execute`](#post-apiv1scriptsscript_idexecute) | Выполнить на нодах |
| GET | [`/api/v1/scripts/{script_id}/executions`](#get-apiv1scriptsscript_idexecutions) | История выполнений |
| POST | [`/api/v1/scripts/{script_id}/schedule`](#post-apiv1scriptsscript_idschedule) | Запланировать скрипт |
| DELETE | [`/api/v1/scripts/{script_id}/schedule`](#delete-apiv1scriptsscript_idschedule) | Отменить расписание |
| GET | [`/api/v1/scripts/{script_id}/schedule`](#get-apiv1scriptsscript_idschedule) | Получить расписание |

### API Keys

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | [`/api/v1/api-keys/`](#post-apiv1api-keys) | Создать API ключ |
| GET | [`/api/v1/api-keys/`](#get-apiv1api-keys) | Список API ключей |
| PATCH | [`/api/v1/api-keys/{key_id}`](#patch-apiv1api-keyskey_id) | Обновить API ключ |
| DELETE | [`/api/v1/api-keys/{key_id}`](#delete-apiv1api-keyskey_id) | Отозвать API ключ |

### Docker

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | [`/api/v1/nodes/{node_id}/docker/containers`](#get-apiv1nodesnode_iddockercontainers) | Список контейнеров |
| GET | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}`](#get-apiv1nodesnode_iddockercontainerscontainer_id) | Детали контейнера |
| POST | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}/start`](#post-apiv1nodesnode_iddockercontainerscontainer_idstart) | Запустить контейнер |
| POST | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}/stop`](#post-apiv1nodesnode_iddockercontainerscontainer_idstop) | Остановить контейнер |
| POST | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}/restart`](#post-apiv1nodesnode_iddockercontainerscontainer_idrestart) | Перезапустить контейнер |
| DELETE | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}`](#delete-apiv1nodesnode_iddockercontainerscontainer_id) | Удалить контейнер |
| GET | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}/logs`](#get-apiv1nodesnode_iddockercontainerscontainer_idlogs) | Логи контейнера |
| POST | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}/exec`](#post-apiv1nodesnode_iddockercontainerscontainer_idexec) | Выполнить команду в контейнере |
| GET | [`/api/v1/nodes/{node_id}/docker/containers/{container_id}/stats`](#get-apiv1nodesnode_iddockercontainerscontainer_idstats) | Статистика контейнера |
| GET | [`/api/v1/nodes/{node_id}/docker/images`](#get-apiv1nodesnode_iddockerimages) | Список образов |
| POST | [`/api/v1/nodes/{node_id}/docker/images/pull`](#post-apiv1nodesnode_iddockerimagespull) | Скачать образ |
| GET | [`/api/v1/nodes/{node_id}/docker/networks`](#get-apiv1nodesnode_iddockernetworks) | Список сетей |
| GET | [`/api/v1/nodes/{node_id}/docker/volumes`](#get-apiv1nodesnode_iddockervolumes) | Список томов |
| POST | [`/api/v1/docker/bulk/start`](#post-apiv1dockerbulkstart) | Bulk-запуск контейнеров |
| POST | [`/api/v1/docker/bulk/stop`](#post-apiv1dockerbulkstop) | Bulk-остановка контейнеров |
| POST | [`/api/v1/docker/bulk/restart`](#post-apiv1dockerbulkrestart) | Bulk-перезапуск контейнеров |
| POST | [`/api/v1/docker/bulk/exec`](#post-apiv1dockerbulkexec) | Bulk-выполнение команд |

### Config

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | [`/api/v1/config/export`](#get-apiv1configexport) | Экспорт конфигурации |
| POST | [`/api/v1/config/import`](#post-apiv1configimport) | Импорт конфигурации |

### WebSocket

| Метод | Endpoint | Описание |
|-------|----------|----------|
| WS | [`/api/v1/nodes/{node_id}/exec-stream`](#ws-apiv1nodesnode_idexec-stream) | Стриминг вывода команд |

### Health

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | [`/health`](#get-health) | Liveness probe |
| GET | [`/ready`](#get-ready) | Readiness probe (проверка БД) |

| Схема | Описание |
|-------|----------|
| [NodeResponse](#noderesponse) | Ответ с данными ноды |
| [PaginatedResponse\<T\>](#paginatedresponset) | Пагинированный ответ |
| [CommandParameter](#commandparameter) | Параметр шаблона команды |
| [CommandCreate](#commandcreate) | Создание команды |
| [CommandUpdate](#commandupdate) | Обновление команды |
| [CommandResponse](#commandresponse) | Ответ с данными команды |
| [CommandExecuteRequest](#commandexecuterequest) | Запрос выполнения команды |
| [CommandResult](#commandresult) | Результат выполнения |
| [TagAdd](#tagadd) | Добавление тега |
| [TagRemove](#tagremove) | Удаление тега |
| [BulkCommandRequest](#bulkcommandrequest) | Bulk-запрос выполнения команд |
| [BulkNodeResult](#bulknoderesult) | Результат по одной ноде |
| [BulkCommandResult](#bulkcommandresult) | Результат bulk-выполнения |
| [ScriptStep](#scriptstep) | Шаг скрипта |
| [ScriptCreate](#scriptcreate) | Создание скрипта |
| [ScriptUpdate](#scriptupdate) | Обновление скрипта |
| [ScriptResponse](#scriptresponse) | Ответ с данными скрипта |
| [ScriptExecuteRequest](#scriptexecuterequest) | Запрос выполнения скрипта |
| [ScriptStepResult](#scriptstepresult) | Результат шага |
| [ScriptNodeResult](#scriptnoderesult) | Результат по ноде |
| [ScriptExecutionBatchResult](#scriptexecutionbatchresult) | Пакетный результат |
| [ScriptExecutionResponse](#scriptexecutionresponse) | Запись выполнения |
| [AuditLogResponse](#auditlogresponse) | Запись аудит-лога |
| [APIKeyCreate](#apikeycreate) | Создание API ключа |
| [APIKeyCreated](#apikeycreated) | Ответ при создании ключа |
| [APIKeyResponse](#apikeyresponse) | Метаданные ключа |
| [APIKeyList](#apikeylist) | Список ключей |
| [DockerContainer](#dockercontainer) | Информация о контейнере |
| [DockerContainerInspect](#dockercontainerinspect) | Детали контейнера (inspect) |
| [DockerExecRequest](#dockerexecrequest) | Запрос exec в контейнере |
| [DockerExecResult](#dockerexecresult) | Результат exec |
| [DockerImage](#dockerimage) | Информация об образе |
| [DockerImagePullRequest](#dockerimagepullrequest) | Запрос скачивания образа |
| [DockerPullResult](#dockerpullresult) | Результат скачивания |
| [DockerStats](#dockerstats) | Статистика контейнера |
| [DockerNetwork](#dockernetwork) | Информация о сети |
| [DockerVolume](#dockervolume) | Информация о томе |

### Ошибки

| HTTP | Описание |
|------|----------|
| [401](#коды-ошибок) | Не авторизован / невалидный API ключ |
| [404](#коды-ошибок) | Ресурс не найден |
| [422](#коды-ошибок) | Ошибка валидации / TemplateRenderError / DockerValidationError |
| [502](#коды-ошибок) | Ошибка Docker-операции на удалённой ноде |
| [503](#коды-ошибок) | Ошибка подключения к ноде / Docker daemon недоступен |

---

## Аутентификация

Все эндпоинты API требуют аутентификации через API ключ в заголовке `X-API-Key`.

### Способы аутентификации

1. **Master Key** — ключ из переменной `MASTER_API_KEY`. Имеет полный доступ ко всем эндпоинтам.
2. **API Key** — ключ, созданный через `/api/v1/api-keys/`. Хранится в БД в хешированном виде.

### Пример запроса

```
GET /api/v1/nodes/ HTTP/1.1
Host: localhost:8000
X-API-Key: nnk_abc123def456...
```

### Ошибки аутентификации

| HTTP | Описание |
|------|----------|
| 401 | Заголовок `X-API-Key` отсутствует или невалиден |
| 401 | API ключ был отозван |

---

## Nodes

### GET /api/v1/nodes/

Список нод с пагинацией, фильтрацией по тегам и поиском. Поддерживает два режима пагинации: offset-based (по умолчанию) и cursor-based.

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `page` | int | 1 | Номер страницы (≥1) |
| `size` | int | 20 | Размер страницы (1–100) |
| `tags` | string \| null | null | Теги через запятую (AND-фильтр) |
| `search` | string \| null | null | Поиск по name или host (ILIKE) |
| `cursor` | string \| null | null | Cursor для keyset pagination (base64) |
| `limit` | int | 20 | Лимит для cursor pagination (1–100) |

> При использовании `cursor` игнорируются `page` и `size`. Cursor возвращается в ответе `CursorPage`.

**Примеры:**

```
GET /api/v1/nodes/?tags=production,web
GET /api/v1/nodes/?search=web-server
GET /api/v1/nodes/?tags=production&search=web&page=1&size=10
```

**Response 200:**

```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "web-server-01",
      "host": "192.168.1.100",
      "port": 22,
      "connection_type": "ssh",
      "status": "active",
      "username": "admin",
      "tags": ["production", "web"],
      "created_at": "2025-07-10T12:00:00Z",
      "updated_at": "2025-07-10T12:00:00Z"
    }
  ],
  "total": 150,
  "page": 1,
  "size": 20
}
```

---

### GET /api/v1/nodes/tags

Получение всех уникальных тегов среди всех нод.

**Response 200:**

```json
["database", "production", "web", "staging"]
```

---

### GET /api/v1/nodes/{node_id}

Получение ноды по ID.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Response 200:** Объект `NodeResponse` (см. выше).

**Response 404:**

```json
{ "detail": "Node not found" }
```

---

### POST /api/v1/nodes/

Создание новой ноды.

**Request Body:**

```json
{
  "name": "web-server-01",
  "host": "192.168.1.100",
  "port": 22,
  "connection_type": "ssh",
  "username": "admin",
  "password": "secret",
  "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
  "tags": ["production", "web"]
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя ноды |
| `host` | string | да | IP или hostname |
| `port` | int | нет (22) | SSH-порт |
| `connection_type` | string | да | Тип подключения: `ssh`, `docker`, `proxmox` |
| `username` | string \| null | нет | Имя пользователя |
| `password` | string \| null | нет | Пароль (шифруется при сохранении) |
| `ssh_key` | string \| null | нет | Приватный SSH-ключ (шифруется при сохранении) |
| `docker_host` | string \| null | нет | Docker daemon URL (обязателен для connection_type=docker) |
| `tags` | list[string] | нет (`[]`) | Теги ноды |

**Response 201:** Объект `NodeResponse`.

---

### PUT /api/v1/nodes/{node_id}

Обновление ноды. Обновляются только переданные поля.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Request Body:**

```json
{
  "name": "new-name",
  "host": "10.0.0.1",
  "status": "unreachable"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя ноды |
| `host` | string \| null | нет | IP или hostname |
| `port` | int \| null | нет | SSH-порт |
| `connection_type` | string \| null | нет | Тип подключения |
| `status` | string \| null | нет | Статус: `active`, `unreachable`, `error` |
| `username` | string \| null | нет | Имя пользователя |
| `password` | string \| null | нет | Пароль |
| `ssh_key` | string \| null | нет | Приватный SSH-ключ |
| `docker_host` | string \| null | нет | Docker daemon URL |
| `tags` | list[string] \| null | нет | Теги ноды |

**Response 200:** Объект `NodeResponse`.

**Response 404:**

```json
{ "detail": "Node not found" }
```

---

### DELETE /api/v1/nodes/{node_id}

Удаление ноды.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Response 204:** Нет тела.

**Response 404:**

```json
{ "detail": "Node not found" }
```

---

### POST /api/v1/nodes/bulk/execute

Bulk-выполнение команды на нескольких нодах по ID и/или тегам. Выполнение параллельное.

**Request Body:**

```json
{
  "command": "uptime",
  "node_ids": [
    "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  ],
  "tags": ["production", "web"]
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `command` | string | да | Команда для выполнения (макс. 4096 символов) |
| `node_ids` | list[UUID] \| null | нет | ID нод (мин. 1) |
| `tags` | list[string] \| null | нет | Теги для фильтрации нод (мин. 1) |

> Обязательно одно из: `node_ids` или `tags`. Если указаны оба — выполняется пересечение (ноды с указанными ID, у которых есть все указанные теги).

**Response 200:**

```json
{
  "command": "uptime",
  "results": [
    {
      "node_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "node_name": "web-server-01",
      "stdout": " 12:00:00 up 10 days, 3:45, 1 user, load average: 0.00, 0.01, 0.05",
      "stderr": "",
      "exit_code": 0
    }
  ],
  "total": 1,
  "succeeded": 1,
  "failed": 0
}
```

**Response 404:**

```json
{ "detail": "No nodes matched the given criteria" }
```

**Response 503:**

```json
{ "detail": "Connection failed: <error message>" }
```

---

### POST /api/v1/nodes/{node_id}/check

Проверка SSH-доступности ноды. Устанавливает статус `active` или `unreachable`.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Response 200:** Объект `NodeResponse` с обновлённым статусом.

**Response 404:**

```json
{ "detail": "Node not found" }
```

**Response 503:**

```json
{ "detail": "Connection failed: <error message>" }
```

---

### POST /api/v1/nodes/{node_id}/execute

Выполнение команды на ноде через SSH.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Request Body:**

```json
{
  "command": "uptime"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `command` | string | да | Команда для выполнения |

**Response 200:**

```json
{
  "stdout": " 12:00:00 up 10 days, 3:45, 1 user, load average: 0.00, 0.01, 0.05",
  "stderr": "",
  "exit_code": 0
}
```

**Response 404:**

```json
{ "detail": "Node not found" }
```

**Response 503:**

```json
{ "detail": "Connection failed: <error message>" }
```

---

### GET /api/v1/nodes/{node_id}/metrics

Получение системных метрик ноды (CPU, память, диск) через SSH.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Response 200:**

```json
{
  "cpu": {
    "usage_percent": 23.4,
    "cores": 4
  },
  "memory": {
    "total_bytes": 8589934592,
    "used_bytes": 4294967296,
    "percent": 50.0
  },
  "disk": {
    "total_bytes": 107374182400,
    "used_bytes": 53687091200,
    "percent": 50.0
  },
  "uptime_since": "2026-01-15 10:30:00"
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `cpu.usage_percent` | float | Использование CPU (0–100) |
| `cpu.cores` | int | Количество ядер |
| `memory.total_bytes` | int | Общий объём памяти (байты) |
| `memory.used_bytes` | int | Используемая память (байты) |
| `memory.percent` | float | Процент использования памяти |
| `disk.total_bytes` | int | Общий объём диска (байты) |
| `disk.used_bytes` | int | Используемый объём диска (байты) |
| `disk.percent` | float | Процент использования диска |
| `uptime_since` | string | Время запуска системы (ISO 8601) |

**Response 404:**

```json
{ "detail": "Node not found" }
```

**Response 503:**

```json
{ "detail": "Connection failed: <error message>" }
```

---

### POST /api/v1/nodes/{node_id}/tags

Добавление тега к ноде.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Request Body:**

```json
{
  "tag": "production"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `tag` | string | да | Тег (1–100 символов) |

**Response 200:** Объект `NodeResponse` с обновлённым списком тегов.

**Response 404:**

```json
{ "detail": "Node not found" }
```

---

### DELETE /api/v1/nodes/{node_id}/tags

Удаление тега у ноды.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Request Body:**

```json
{
  "tag": "production"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `tag` | string | да | Тег для удаления |

**Response 200:** Объект `NodeResponse` с обновлённым списком тегов.

**Response 404:**

```json
{ "detail": "Node not found" }
```

---

## Audit

### GET /api/v1/audit/

Получение аудит-лога с фильтрами и пагинацией.

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `node_id` | UUID \| null | null | Фильтр по ID ноды |
| `action` | string \| null | null | Фильтр по типу действия |
| `page` | int | 1 | Номер страницы (≥1) |
| `size` | int | 20 | Размер страницы (1–100) |

**Response 200:**

```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "node_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "action": "create",
      "user": "admin",
      "details": "Created node web-server-01",
      "created_at": "2025-07-10T12:00:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "size": 20
}
```

---

### DELETE /api/v1/audit/

Удаление всех записей аудит-лога. Требует master key и параметр подтверждения.

**Query Parameters:**

| Параметр | Тип | Обязательно | Описание |
|----------|-----|-------------|----------|
| `confirm` | string | да | Значение `yes` для подтверждения |

**Response 200:**

```json
{ "deleted_count": 42 }
```

**Response 403:**

```json
{ "detail": "Only master key can delete all audit logs" }
```

**Response 422:**

```json
{ "detail": "Add ?confirm=yes to confirm deletion of all audit logs" }
```

---

## Commands

Шаблоны команд с параметрами. Позволяют сохранять часто используемые команды и выполнять их на нодах с подстановкой параметров.

### GET /api/v1/commands/

Список команд с пагинацией.

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `page` | int | 1 | Номер страницы (≥1) |
| `size` | int | 20 | Размер страницы (1–100) |
| `tag` | string \| null | null | Фильтр по тегу (AND) |

**Response 200:**

```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "check-disk",
      "description": "Проверка дискового пространства",
      "command": "df -h {mount_point}",
      "parameters": [
        {
          "name": "mount_point",
          "type": "string",
          "required": true,
          "default": null,
          "description": "Точка монтирования"
        }
      ],
      "created_at": "2025-07-10T12:00:00Z",
      "updated_at": "2025-07-10T12:00:00Z"
    }
  ],
  "total": 5,
  "page": 1,
  "size": 20
}
```

---

### GET /api/v1/commands/{command_id}

Получение команды по ID.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `command_id` | UUID | ID команды |

**Response 200:** Объект `CommandResponse` (см. выше).

**Response 404:**

```json
{ "detail": "Command not found" }
```

---

### POST /api/v1/commands/

Создание нового шаблона команды.

**Request Body:**

```json
{
  "name": "check-disk",
  "description": "Проверка дискового пространства",
  "command": "df -h {mount_point}",
  "parameters": [
    {
      "name": "mount_point",
      "type": "string",
      "required": true,
      "default": null,
      "description": "Точка монтирования"
    }
  ]
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя команды (уникальное) |
| `description` | string \| null | нет | Описание |
| `command` | string | да | Шаблон команды (с `{placeholder}`) |
| `parameters` | list | нет | Список параметров шаблона |

**Response 201:** Объект `CommandResponse`.

---

### PUT /api/v1/commands/{command_id}

Обновление шаблона команды. Обновляются только переданные поля.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `command_id` | UUID | ID команды |

**Request Body:**

```json
{
  "name": "check-disk-extended",
  "command": "df -h {mount_point} && du -sh {path}"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя команды |
| `description` | string \| null | нет | Описание |
| `command` | string \| null | нет | Шаблон команды |
| `parameters` | list \| null | нет | Список параметров |

**Response 200:** Объект `CommandResponse`.

**Response 404:**

```json
{ "detail": "Command not found" }
```

---

### DELETE /api/v1/commands/{command_id}

Удаление шаблона команды.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `command_id` | UUID | ID команды |

**Response 204:** Нет тела.

**Response 404:**

```json
{ "detail": "Command not found" }
```

---

### POST /api/v1/commands/{command_id}/execute

Выполнение шаблона команды на ноде с подстановкой параметров.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `command_id` | UUID | ID команды |

**Request Body:**

```json
{
  "node_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "params": {
    "mount_point": "/",
    "path": "/var/log"
  }
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `node_id` | UUID | да | ID ноды для выполнения |
| `params` | dict | нет | Значения параметров шаблона |

**Response 200:**

```json
{
  "stdout": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       50G   12G   36G  25% /",
  "stderr": "",
  "exit_code": 0
}
```

**Response 404:**

```json
{ "detail": "Command not found" }
```

**Response 422 (TemplateRenderError):**

```json
{ "detail": "Missing required parameters: mount_point" }
```

**Response 503:**

```json
{ "detail": "Failed to execute command on node ...: <error>" }
```

---

## Scripts

Пайплайны команд (скрипты) — упорядоченные последовательности шагов, выполняемых на одной или нескольких нодах. Каждый шаг может быть inline-командой или ссылкой на сохранённый шаблон команды.

### GET /api/v1/scripts/

Список скриптов с пагинацией.

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `page` | int | 1 | Номер страницы (≥1) |
| `size` | int | 20 | Размер страницы (1–100) |
| `tag` | string \| null | null | Фильтр по тегу (AND) |

**Response 200:**

```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "deploy-check",
      "description": "Проверка после деплоя",
      "steps": [
        {
          "label": "Проверка сервиса",
          "type": "command",
          "command": null,
          "command_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
          "params": {},
          "on_failure": "stop"
        },
        {
          "label": "Проверка логов",
          "type": "inline",
          "command": "tail -n 50 /var/log/app.log",
          "command_id": null,
          "params": {},
          "on_failure": "continue"
        }
      ],
      "created_at": "2025-07-10T12:00:00Z",
      "updated_at": "2025-07-10T12:00:00Z"
    }
  ],
  "total": 3,
  "page": 1,
  "size": 20
}
```

---

### GET /api/v1/scripts/{script_id}

Получение скрипта по ID.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `script_id` | UUID | ID скрипта |

**Response 200:** Объект `ScriptResponse` (см. выше).

**Response 404:**

```json
{ "detail": "Script not found" }
```

---

### POST /api/v1/scripts/

Создание нового скрипта.

**Request Body:**

```json
{
  "name": "deploy-check",
  "description": "Проверка после деплоя",
  "steps": [
    {
      "label": "Проверка сервиса",
      "type": "command",
      "command_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "params": {},
      "on_failure": "stop"
    },
    {
      "label": "Проверка логов",
      "type": "inline",
      "command": "tail -n 50 /var/log/app.log",
      "params": {},
      "on_failure": "continue"
    }
  ]
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя скрипта (уникальное) |
| `description` | string \| null | нет | Описание |
| `steps` | list[ScriptStep] | да | Шаги скрипта (мин. 1) |

**ScriptStep:**

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `label` | string | да | Название шага |
| `type` | `"inline"` \| `"command"` | да | Тип: inline-команда или ссылка на шаблон |
| `command` | string \| null | нет | Команда (для type=`inline`) |
| `command_id` | UUID \| null | нет | ID шаблона команды (для type=`command`) |
| `params` | dict | нет | Параметры шага |
| `on_failure` | `"stop"` \| `"continue"` | нет (stop) | Поведение при ошибке |

**Response 201:** Объект `ScriptResponse`.

---

### PUT /api/v1/scripts/{script_id}

Обновление скрипта. Обновляются только переданные поля.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `script_id` | UUID | ID скрипта |

**Request Body:**

```json
{
  "name": "deploy-check-v2",
  "steps": [
    {
      "label": "Обновлённый шаг",
      "type": "inline",
      "command": "systemctl status app",
      "on_failure": "stop"
    }
  ]
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя скрипта |
| `description` | string \| null | нет | Описание |
| `steps` | list[ScriptStep] | нет | Новые шаги |

**Response 200:** Объект `ScriptResponse`.

**Response 404:**

```json
{ "detail": "Script not found" }
```

---

### DELETE /api/v1/scripts/{script_id}

Удаление скрипта.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `script_id` | UUID | ID скрипта |

**Response 204:** Нет тела.

**Response 404:**

```json
{ "detail": "Script not found" }
```

---

### POST /api/v1/scripts/{script_id}/execute

Выполнение скрипта на нескольких нодах параллельно.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `script_id` | UUID | ID скрипта |

**Request Body:**

```json
{
  "node_ids": [
    "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  ],
  "params": {
    "version": "1.2.3"
  }
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `node_ids` | list[UUID] | да | ID нод для выполнения (мин. 1) |
| `params` | dict | нет | Глобальные параметры для подстановки |

**Response 200:**

```json
{
  "script_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "results": [
    {
      "execution_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "node_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "node_name": "web-server-01",
      "status": "completed",
      "steps": [
        {
          "step_index": 0,
          "label": "Проверка сервиса",
          "command": "systemctl status app",
          "stdout": "active (running)",
          "stderr": "",
          "exit_code": 0
        }
      ]
    }
  ]
}
```

**Response 404:**

```json
{ "detail": "Script not found" }
```

**Response 422 (TemplateRenderError):**

```json
{ "detail": "Missing required parameters: version" }
```

**Response 503:**

```json
{ "detail": "Failed to execute command on node ...: <error>" }
```

---

### GET /api/v1/scripts/{script_id}/executions

История выполнений скрипта с пагинацией.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `script_id` | UUID | ID скрипта |

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `page` | int | 1 | Номер страницы (≥1) |
| `size` | int | 20 | Размер страницы (1–100) |

**Response 200:**

```json
{
  "items": [
    {
      "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "script_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "node_id": "550e8400-e29b-41d4-a716-446655440000",
      "params": {"version": "1.2.3"},
      "status": "completed",
      "steps": [
        {
          "step_index": 0,
          "label": "Проверка сервиса",
          "command": "systemctl status app",
          "stdout": "active (running)",
          "stderr": "",
          "exit_code": 0
        }
      ],
      "started_at": "2025-07-10T12:00:00Z",
      "finished_at": "2025-07-10T12:00:05Z"
    }
  ],
  "total": 10,
  "page": 1,
  "size": 20
}
```

**Response 404:**

```json
{ "detail": "Script not found" }
```

---

### Script Scheduler

#### POST /api/v1/scripts/{script_id}/schedule

Запланировать выполнение скрипта по cron-выражению.

**Request:**

```json
{
  "cron": "0 9 * * *",
  "node_ids": ["00000000-0000-0000-0000-000000000001"]
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `cron` | string | Cron-выражение (минимум 5 полей) |
| `node_ids` | UUID[] | ID нод для выполнения (минимум 1) |

**Response 200:**

```json
{
  "script_id": "550e8400-e29b-41d4-a716-446655440000",
  "cron": "0 9 * * *",
  "message": "Script scheduled successfully"
}
```

**Response 422:**

```json
{ "detail": "Invalid cron expression" }
```

---

#### DELETE /api/v1/scripts/{script_id}/schedule

Отменить расписание скрипта.

**Response 200:**

```json
{
  "message": "Script unscheduled",
  "script_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response 404:**

```json
{ "detail": "No schedule found for script" }
```

---

#### GET /api/v1/scripts/{script_id}/schedule

Получить информацию о расписании скрипта.

**Response 200:**

```json
{
  "script_id": "550e8400-e29b-41d4-a716-446655440000",
  "cron": "0 9 * * *",
  "next_run_time": "2026-07-27T09:00:00",
  "node_ids": ["00000000-0000-0000-0000-000000000001"]
}
```

**Response 404:**

```json
{ "detail": "No schedule found for script" }
```

---

## API Keys

Управление API ключами для аутентификации.

### POST /api/v1/api-keys/

Создание нового API ключа. Полный ключ возвращается только один раз при создании.

**Request Body:**

```json
{
  "name": "my-app-key",
  "scope": "read-write"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя ключа (1–255 символов) |
| `scope` | string | нет (`read-write`) | Scope: `read-only` или `read-write` |

**Response 201:**

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "my-app-key",
  "key": "nnk_dYU4Rb65xK9mN2pQ...",
  "key_prefix": "nnk_dYU4",
  "created_at": "2025-07-10T12:00:00Z"
}
```

> **Важно:** Значение `key` показывается только при создании. Сохраните его — повторное получение невозможно.

---

### GET /api/v1/api-keys/

Список API ключей (без самих ключей, только метаданные).

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `page` | int | 1 | Номер страницы (≥1) |
| `size` | int | 20 | Размер страницы (1–100) |

**Response 200:**

```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "my-app-key",
      "key_prefix": "nnk_dYU4",
      "is_active": true,
      "created_at": "2025-07-10T12:00:00Z",
      "last_used_at": "2025-07-10T14:30:00Z"
    }
  ],
  "total": 3
}
```

---

### PATCH /api/v1/api-keys/{key_id}

Обновление API ключа (имя, активность, scope, срок действия).

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `key_id` | UUID | ID ключа |

**Request Body:**

```json
{
  "name": "new-name",
  "is_active": false,
  "scope": "read-only",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя ключа (1–255 символов) |
| `is_active` | bool \| null | нет | Активен ли ключ |
| `scope` | string \| null | нет | Scope: `read-only` или `read-write` |
| `expires_at` | datetime \| null | нет | Дата и время истечения ключа |

> Все поля опциональны. Обновляются только переданные поля.

**Response 200:**

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "new-name",
  "key_prefix": "nnk_dYU4",
  "is_active": false,
  "scope": "read-only",
  "created_at": "2025-07-10T12:00:00Z",
  "last_used_at": null,
  "expires_at": "2026-12-31T23:59:59Z"
}
```

**Response 404:**

```json
{ "detail": "API key not found" }
```

---

### DELETE /api/v1/api-keys/{key_id}

Отзыв API ключа. Отозванный ключ перестаёт работать.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `key_id` | UUID | ID ключа |

**Response 204:** Нет тела.

**Response 404:**

```json
{ "detail": "API key not found" }
```

---

## Config

Экспорт и импорт конфигурации (ноды, команды, скрипты). Секреты (пароли, SSH-ключи) исключаются из экспорта.

### GET /api/v1/config/export

Экспортировать все ноды, команды и скрипты.

**Response 200:**

```json
{
  "version": "0.6.0",
  "exported_at": "2026-07-26T12:00:00Z",
  "nodes": [
    {
      "name": "web-server",
      "host": "10.0.0.1",
      "port": 22,
      "connection_type": "ssh",
      "username": "root",
      "tags": ["prod", "web"]
    }
  ],
  "commands": [
    {
      "name": "check-disk",
      "description": "Проверить свободное место",
      "command": "df -h {mount_point}",
      "parameters": [
        {"name": "mount_point", "type": "string", "required": true}
      ],
      "tags": ["monitoring"]
    }
  ],
  "scripts": [
    {
      "name": "deploy-app",
      "description": "Деплой приложения",
      "steps": [
        {"label": "Pull", "type": "inline", "command": "git pull"}
      ],
      "tags": ["deploy"]
    }
  ]
}
```

---

### POST /api/v1/config/import

Импортировать конфигурацию. Дубликаты по имени пропускаются.

**Request:**

```json
{
  "nodes": [
    {
      "name": "web-server",
      "host": "10.0.0.1",
      "port": 22,
      "connection_type": "ssh",
      "username": "root",
      "tags": ["prod"]
    }
  ],
  "commands": [],
  "scripts": []
}
```

**Response 200:**

```json
{
  "nodes_created": 1,
  "commands_created": 0,
  "scripts_created": 0,
  "errors": []
}
```

---

## WebSocket

### WS /api/v1/nodes/{node_id}/exec-stream

Стриминг вывода команд через WebSocket. Аутентификация через query-параметр `?token=<api_key>`.

**Подключение:**
```
ws://localhost:8000/api/v1/nodes/{node_id}/exec-stream?token=nnk_abc123...
```

**Клиент → Сервер (JSON):**

```json
{"command": "ls -la"}
{"type": "signal", "signal": "SIGINT"}
```

**Сервер → Клиент (JSON):**

```json
{"type": "stdout", "data": "output line 1\n"}
{"type": "done", "exit_code": 0}
{"type": "error", "message": "SSH connection failed"}
```

Коды закрытия:
| Код | Причина |
|-----|---------|
| 4001 | Отсутствует токен |
| 4003 | Невалидный API ключ |
| 4004 | Нода не найдена |
| 1011 | Внутренняя ошибка |

---

## Docker

Управление Docker контейнерами, образами, сетями и томами на нодах. Все Docker операции выполняются через SSH на удалённой ноде.

Base URL для Docker: `/api/v1/nodes/{node_id}/docker`

### GET /api/v1/nodes/{node_id}/docker/containers

Список контейнеров на ноде.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `all` | bool | false | Показывать остановленные контейнеры |

**Response 200:**

```json
[
  {
    "ID": "abc123def456",
    "Names": "/my-container",
    "Image": "nginx:latest",
    "Command": "/docker-entrypoint.sh",
    "CreatedAt": "2025-07-10 12:00:00 +0000 UTC",
    "State": "running",
    "Status": "Up 2 days",
    "Ports": "0.0.0.0:8080->80/tcp",
    "Networks": "bridge"
  }
]
```

**Response 404:**

```json
{ "detail": "Node not found" }
```

**Response 502:**

```json
{ "detail": "Docker error: <message>" }
```

---

### GET /api/v1/nodes/{node_id}/docker/containers/{container_id}

Детали контейнера (аналог `docker inspect`).

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера (hex + дефисы) |

**Response 200:**

```json
{
  "Id": "abc123def456...",
  "Name": "/my-container",
  "State": {
    "status": "running",
    "running": true,
    "exit_code": 0,
    "started_at": "2025-07-10T12:00:00Z",
    "finished_at": null,
    "oom_killed": null
  },
  "Config": {
    "image": "nginx:latest",
    "cmd": ["/docker-entrypoint.sh"],
    "env": ["PATH=/usr/local/sbin:/usr/local/bin"],
    "hostname": "abc123def456"
  },
  "NetworkSettings": {}
}
```

**Response 404:**

```json
{ "detail": "Container not found" }
```

**Response 422 (DockerValidationError):**

```json
{ "detail": "Invalid container ID format: ..." }
```

---

### POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/start

Запуск контейнера.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера |

**Response 204:** Нет тела.

---

### POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/stop

Остановка контейнера.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера |

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `timeout` | int | 10 | Таймаут остановки (1–300 сек) |

**Response 204:** Нет тела.

---

### POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/restart

Перезапуск контейнера.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера |

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `timeout` | int | 10 | Таймаут остановки перед перезапуском (1–300 сек) |

**Response 204:** Нет тела.

---

### DELETE /api/v1/nodes/{node_id}/docker/containers/{container_id}

Удаление контейнера.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера |

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `force` | bool | false | Принудительное удаление |

**Response 204:** Нет тела.

---

### GET /api/v1/nodes/{node_id}/docker/containers/{container_id}/logs

Получение логов контейнера.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера |

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `tail` | int | 100 | Количество строк с конца (1–10000) |
| `since` | string \| null | null | Время начала (unix timestamp или Go duration) |

**Response 200:** Текст логов (plain text string).

---

### POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/exec

Выполнение команды в контейнере (аналог `docker exec`).

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера |

**Request Body:**

```json
{
  "command": "ls -la /app",
  "timeout": 30
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `command` | string | да | Команда (1–4096 символов) |
| `timeout` | int | нет (30) | Таймаут (1–600 сек) |

**Response 200:**

```json
{
  "stdout": "total 64\ndrwxr-xr-x 12 root root 4096 ...",
  "stderr": "",
  "exit_code": 0
}
```

---

### GET /api/v1/nodes/{node_id}/docker/containers/{container_id}/stats

Статистика контейнера (аналог `docker stats --no-stream`).

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |
| `container_id` | string | ID контейнера |

**Response 200:**

```json
{
  "Container": "abc123def456",
  "Name": "my-container",
  "CPUPerc": "0.15%",
  "MemUsage": "12.3MiB / 256MiB",
  "MemLimit": "256MiB",
  "MemPerc": "4.80%",
  "NetIO": "1.2MB / 500kB",
  "BlockIO": "10MB / 0B",
  "PIDs": "5"
}
```

---

### GET /api/v1/nodes/{node_id}/docker/images

Список Docker образов на ноде.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Response 200:**

```json
[
  {
    "Repository": "nginx",
    "Tag": "latest",
    "ID": "abc123def456",
    "Size": "187MB",
    "CreatedAt": "2025-07-01 00:00:00 +0000 UTC"
  }
]
```

---

### POST /api/v1/nodes/{node_id}/docker/images/pull

Скачивание Docker образа на ноду.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Request Body:**

```json
{
  "image": "nginx:1.25",
  "timeout": 300
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `image` | string | да | Имя образа (1–255 символов) |
| `timeout` | int | нет (300) | Таймаут (1–3600 сек) |

**Response 200:**

```json
{
  "image": "nginx:1.25",
  "output": "Status: Downloaded newer image for nginx:1.25",
  "success": true
}
```

---

### GET /api/v1/nodes/{node_id}/docker/networks

Список Docker сетей на ноде.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Response 200:**

```json
[
  {
    "ID": "abc123def456",
    "Name": "bridge",
    "Driver": "bridge",
    "Scope": "local"
  }
]
```

---

### GET /api/v1/nodes/{node_id}/docker/volumes

Список Docker томов на ноде.

**Path Parameters:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `node_id` | UUID | ID ноды |

**Response 200:**

```json
[
  {
    "Driver": "local",
    "Name": "my-volume"
  }
]
```

---

## Docker Bulk

Bulk-операции выполняются параллельно (`asyncio.gather`) на нескольких нодах.

Base URL: `/api/v1/docker`

### POST /api/v1/docker/bulk/start

Запустить контейнер на нескольких нодах.

**Request:**

```json
{
  "node_ids": ["uuid-1", "uuid-2"],
  "container_id": "my-container"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `node_ids` | string[] | да | ID нод (минимум 1) |
| `container_id` | string | да | ID или имя контейнера |
| `timeout` | int \| null | нет | Таймаут в секундах (1–300) |
| `command` | string \| null | нет | Команда (только для `/bulk/exec`) |

**Response 200:**

```json
{
  "action": "start",
  "results": [
    {"node_id": "uuid-1", "node_name": "web-1", "status": "success", "output": "my-container"},
    {"node_id": "uuid-2", "node_name": "web-2", "status": "error", "error": "Container not found"}
  ],
  "total": 2,
  "succeeded": 1,
  "failed": 1
}
```

---

### POST /api/v1/docker/bulk/stop

Остановить контейнер на нескольких нодах. Принимает `timeout` (по умолчанию 10с).

---

### POST /api/v1/docker/bulk/restart

Перезапустить контейнер на нескольких нодах. Принимает `timeout` (по умолчанию 10с).

---

### POST /api/v1/docker/bulk/exec

Выполнить команду в контейнере на нескольких нодах. Поле `command` обязательно.

---

## Health

### GET /health

Liveness probe — проверяет, что процесс работает. Не требует аутентификации (для Kubernetes liveness probes).

**Response 200:**

```json
{ "status": "healthy", "version": "0.4.0" }
```

| Поле | Тип | Описание |
|------|-----|----------|
| `status` | string | Статус: `healthy` |
| `version` | string | Версия приложения |

---

### GET /ready

Readiness probe — проверяет доступность базы данных. Не требует аутентификации (для Kubernetes readiness probes).

**Response 200:**

```json
{ "status": "ready", "checks": { "database": "ok" } }
```

**Response 503:**

```json
{ "status": "not_ready", "checks": { "database": "error" } }
```

| Поле | Тип | Описание |
|------|-----|----------|
| `status` | string | Статус: `ready` или `not_ready` |
| `checks` | object | Результаты проверок |
| `checks.database` | string | `ok` или `error` |

---

## Общие схемы

### NodeResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `name` | string | Имя ноды |
| `host` | string | IP или hostname |
| `port` | int | Порт |
| `connection_type` | string | Тип подключения |
| `status` | string | Статус: `active`, `unreachable`, `error` |
| `username` | string \| null | Имя пользователя |
| `docker_host` | string \| null | Docker daemon URL |
| `tags` | list[string] | Теги ноды |
| `created_at` | datetime | Время создания |
| `updated_at` | datetime | Время обновления |

> **Примечание:** Поля `password` и `ssh_key` **никогда** не возвращаются в ответе.

### PaginatedResponse\<T\>

| Поле | Тип | Описание |
|------|-----|----------|
| `items` | list\<T\> | Список объектов |
| `total` | int | Общее количество |
| `page` | int | Текущая страница |
| `size` | int | Размер страницы |

### CommandParameter

| Поле | Тип | Описание |
|------|-----|----------|
| `name` | string | Имя параметра |
| `type` | string | Тип: `string`, `integer`, `boolean` |
| `required` | bool | Обязательный (по умолчанию true) |
| `default` | any | Значение по умолчанию |
| `description` | string \| null | Описание параметра |

### CommandCreate

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя команды |
| `description` | string \| null | нет | Описание |
| `command` | string | да | Шаблон команды с `{placeholder}` |
| `parameters` | list[CommandParameter] | нет | Параметры шаблона |
| `tags` | list[string] | нет | Теги команды |

### CommandUpdate

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя команды |
| `description` | string \| null | нет | Описание |
| `command` | string \| null | нет | Шаблон команды |
| `parameters` | list[CommandParameter] \| null | нет | Параметры |
| `tags` | list[string] \| null | нет | Теги команды |

### CommandResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `name` | string | Имя команды |
| `description` | string \| null | Описание |
| `command` | string | Шаблон команды |
| `parameters` | list[CommandParameter] \| null | Параметры |
| `tags` | list[string] | Теги команды |
| `created_at` | datetime | Время создания |
| `updated_at` | datetime | Время обновления |

### CommandExecuteRequest

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `node_id` | UUID | да | ID ноды для выполнения |
| `params` | dict | нет | Значения параметров |

### CommandResult

| Поле | Тип | Описание |
|------|-----|----------|
| `stdout` | string | Стандартный вывод |
| `stderr` | string | Стандартный вывод ошибок |
| `exit_code` | int | Код возврата |

### TagAdd

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `tag` | string | да | Тег (1–100 символов) |

### TagRemove

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `tag` | string | да | Тег для удаления |

### BulkCommandRequest

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `command` | string | да | Команда для выполнения (макс. 4096 символов) |
| `node_ids` | list[UUID] \| null | нет | ID нод (мин. 1) |
| `tags` | list[string] \| null | нет | Теги для фильтрации нод (мин. 1) |

> Обязательно одно из: `node_ids` или `tags`.

### BulkNodeResult

| Поле | Тип | Описание |
|------|-----|----------|
| `node_id` | UUID | ID ноды |
| `node_name` | string | Имя ноды |
| `stdout` | string | Стандартный вывод |
| `stderr` | string | Стандартный вывод ошибок |
| `exit_code` | int | Код возврата |

### BulkCommandResult

| Поле | Тип | Описание |
|------|-----|----------|
| `command` | string | Выполненная команда |
| `results` | list[BulkNodeResult] | Результаты по нодам |
| `total` | int | Общее количество нод |
| `succeeded` | int | Успешных выполнений |
| `failed` | int | Неудачных выполнений |

### ScriptStep

| Поле | Тип | Описание |
|------|-----|----------|
| `label` | string | Название шага |
| `type` | `"inline"` \| `"command"` | Тип шага |
| `command` | string \| null | Inline-команда |
| `command_id` | UUID \| null | ID шаблона команды |
| `params` | dict | Параметры шага |
| `on_failure` | `"stop"` \| `"continue"` | Поведение при ошибке |

### ScriptCreate

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя скрипта |
| `description` | string \| null | нет | Описание |
| `steps` | list[ScriptStep] | да | Шаги скрипта (мин. 1) |
| `tags` | list[string] | нет | Теги скрипта |

### ScriptUpdate

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя скрипта |
| `description` | string \| null | нет | Описание |
| `steps` | list[ScriptStep] | нет | Шаги скрипта |
| `tags` | list[string] \| null | нет | Теги скрипта |

### ScriptResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `name` | string | Имя скрипта |
| `description` | string \| null | Описание |
| `steps` | list[ScriptStep] | Шаги скрипта |
| `tags` | list[string] | Теги скрипта |
| `created_at` | datetime | Время создания |
| `updated_at` | datetime | Время обновления |

### ScriptExecuteRequest

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `node_ids` | list[UUID] | да | ID нод для выполнения (мин. 1) |
| `params` | dict | нет | Глобальные параметры |

### ScriptStepResult

| Поле | Тип | Описание |
|------|-----|----------|
| `step_index` | int | Индекс шага |
| `label` | string | Название шага |
| `command` | string | Выполненная команда |
| `stdout` | string | Стандартный вывод |
| `stderr` | string | Стандартный вывод ошибок |
| `exit_code` | int | Код возврата |

### ScriptNodeResult

| Поле | Тип | Описание |
|------|-----|----------|
| `execution_id` | UUID | ID выполнения |
| `node_id` | UUID | ID ноды |
| `node_name` | string | Имя ноды |
| `status` | string | Статус: `completed`, `failed`, `running` |
| `steps` | list[ScriptStepResult] | Результаты шагов |

### ScriptExecutionBatchResult

| Поле | Тип | Описание |
|------|-----|----------|
| `script_id` | UUID | ID скрипта |
| `results` | list[ScriptNodeResult] | Результаты по нодам |

### ScriptExecutionResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `script_id` | UUID | ID скрипта |
| `node_id` | UUID \| null | ID ноды |
| `params` | dict \| null | Параметры выполнения |
| `status` | string | Статус выполнения |
| `steps` | list[dict] \| null | Результаты шагов |
| `started_at` | datetime | Время начала |
| `finished_at` | datetime \| null | Время завершения |

### CommandRequest

| Поле | Тип | Описание |
|------|-----|----------|
| `command` | string | Команда для выполнения |
| `timeout` | int \| null | Таймаут в секундах (1–600) |

### CommandResult (Nodes API)

| Поле | Тип | Описание |
|------|-----|----------|
| `stdout` | string | Стандартный вывод |
| `stderr` | string | Стандартный вывод ошибок |
| `exit_code` | int | Код возврата |

### AuditLogResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `node_id` | UUID \| null | ID связанной ноды |
| `action` | string | Тип действия |
| `user` | string \| null | Пользователь |
| `details` | string \| null | Детали |
| `created_at` | datetime | Время создания |

### APIKeyCreate

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя ключа (1–255 символов) |
| `scope` | string | нет (`read-write`) | Scope: `read-only` или `read-write` |

### APIKeyCreated

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `name` | string | Имя ключа |
| `key` | string | Полный ключ (только при создании) |
| `key_prefix` | string | Префикс ключа для идентификации |
| `created_at` | datetime | Время создания |

### APIKeyResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `name` | string | Имя ключа |
| `key_prefix` | string | Префикс ключа |
| `is_active` | bool | Активен ли ключ |
| `created_at` | datetime | Время создания |
| `last_used_at` | datetime \| null | Время последнего использования |
| `scope` | string | `read-write` или `read-only` |
| `expires_at` | datetime \| null | Дата истечения |

### APIKeyList

| Поле | Тип | Описание |
|------|-----|----------|
| `items` | list[APIKeyResponse] | Список ключей |
| `total` | int | Общее количество |

### DockerContainer

| Поле | Тип | Описание |
|------|-----|----------|
| `ID` | string | ID контейнера |
| `Names` | string | Имя контейнера |
| `Image` | string | Образ |
| `Command` | string | Команда запуска |
| `CreatedAt` | string | Время создания |
| `State` | string | Состояние: `running`, `exited`, etc. |
| `Status` | string | Статус (человекочитаемый) |
| `Ports` | string \| null | порты |
| `Networks` | string \| null | Сети |

### DockerContainerInspect

| Поле | Тип | Описание |
|------|-----|----------|
| `Id` | string | ID контейнера |
| `Name` | string | Имя |
| `State` | DockerContainerState | Состояние |
| `Config` | DockerContainerConfig | Конфигурация |
| `NetworkSettings` | dict \| null | Сетевые настройки |

### DockerContainerState

| Поле | Тип | Описание |
|------|-----|----------|
| `status` | string | Статус |
| `running` | bool | Запущен |
| `exit_code` | int | Код выхода |
| `started_at` | string \| null | Время запуска |
| `finished_at` | string \| null | Время остановки |
| `oom_killed` | bool \| null | Убит OOM |

### DockerContainerConfig

| Поле | Тип | Описание |
|------|-----|----------|
| `image` | string \| null | Образ |
| `cmd` | list[string] \| null | Команда |
| `env` | list[string] \| null | Переменные окружения |
| `hostname` | string \| null | Хостнейм |

### DockerExecRequest

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `command` | string | да | Команда (1–4096 символов) |
| `timeout` | int | нет (30) | Таймаут (1–600 сек) |

### DockerExecResult

| Поле | Тип | Описание |
|------|-----|----------|
| `stdout` | string | Стандартный вывод |
| `stderr` | string | Стандартный вывод ошибок |
| `exit_code` | int | Код возврата |

### DockerImage

| Поле | Тип | Описание |
|------|-----|----------|
| `Repository` | string | Репозиторий |
| `Tag` | string | Тег |
| `ID` | string | ID образа |
| `Size` | string | Размер |
| `CreatedAt` | string | Время создания |

### DockerImagePullRequest

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `image` | string | да | Имя образа (1–255 символов) |
| `timeout` | int | нет (300) | Таймаут (1–3600 сек) |

### DockerPullResult

| Поле | Тип | Описание |
|------|-----|----------|
| `image` | string | Имя образа |
| `output` | string | Вывод операции |
| `success` | bool | Успешно |

### DockerStats

| Поле | Тип | Описание |
|------|-----|----------|
| `Container` | string | ID контейнера |
| `Name` | string | Имя |
| `CPUPerc` | string | Процент CPU |
| `MemUsage` | string | Использование памяти |
| `MemLimit` | string \| null | Лимит памяти |
| `MemPerc` | string | Процент памяти |
| `NetIO` | string | сетевой I/O |
| `BlockIO` | string | блочный I/O |
| `PIDs` | string \| null | Количество процессов |

### DockerNetwork

| Поле | Тип | Описание |
|------|-----|----------|
| `ID` | string | ID сети |
| `Name` | string | Имя |
| `Driver` | string | Драйвер |
| `Scope` | string | Область |

### DockerVolume

| Поле | Тип | Описание |
|------|-----|----------|
| `Driver` | string | Драйвер |
| `Name` | string | Имя |

---

### CursorPage

Cursor-based keyset pagination. Fields: `items`, `next_cursor`, `has_more`, `limit`.

### BulkDockerRequest

Fields: `node_ids`, `container_id`, `timeout`, `command`.

### BulkDockerResponse

Fields: `action`, `results`, `total`, `succeeded`, `failed`.

### ScheduleRequest

Fields: `cron` (5-field cron expression), `node_ids` (list of UUIDs).

### ScheduleResponse

Fields: `script_id`, `cron`, `message`.

### NodeMetrics

Fields: `cpu` (usage_percent, cores), `memory` (total_bytes, used_bytes, percent),
`disk` (total_bytes, used_bytes, percent), `uptime_since`.

### ConfigExport

Fields: `version`, `exported_at`, `nodes` (no secrets), `commands`, `scripts`.

### ImportResult

Fields: `nodes_created`, `commands_created`, `scripts_created`, `errors`.

---

## Коды ошибок

| HTTP | Описание |
|------|----------|
| 201 | Создано успешно |
| 204 | Удалено успешно |
| 401 | Не авторизован / невалидный / отозван / истёк API ключ |
| 403 | Недостаточно прав (read-only ключ на write-операции) |
| 404 | Ресурс не найден |
| 422 | Ошибка валидации / TemplateRenderError / DockerValidationError |
| 429 | Превышен лимит запросов (rate limiting) |
| 502 | Ошибка Docker-операции |
| 503 | Ошибка подключения к ноде |
| 504 | Превышен таймаут запроса (RequestTimeoutError) |
