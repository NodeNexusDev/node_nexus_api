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
| [Nodes](#nodes) | CRUD ноды, проверка доступности, SSH-команды |
| [Audit](#audit) | Аудит-лог операций |
| [Commands](#commands) | Шаблоны команд с параметрами |
| [Scripts](#scripts) | Пайплайны команд (скрипты) |
| [API Keys](#api-keys) | Управление API ключами |
| [Docker](#docker) | Управление Docker контейнерами на нодах |
| [Health](#health) | Healthcheck |

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
| GET | [`/api/v1/scripts/`](#get-apiv1scripts) | Список скриптов |
| GET | [`/api/v1/scripts/{script_id}`](#get-apiv1scriptsscript_id) | Скрипт по ID |
| POST | [`/api/v1/scripts/`](#post-apiv1scripts) | Создать скрипт |
| PUT | [`/api/v1/scripts/{script_id}`](#put-apiv1scriptsscript_id) | Обновить скрипт |
| DELETE | [`/api/v1/scripts/{script_id}`](#delete-apiv1scriptsscript_id) | Удалить скрипт |
| POST | [`/api/v1/scripts/{script_id}/execute`](#post-apiv1scriptsscript_idexecute) | Выполнить на нодах |
| GET | [`/api/v1/scripts/{script_id}/executions`](#get-apiv1scriptsscript_idexecutions) | История выполнений |

### API Keys

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | [`/api/v1/api-keys/`](#post-apiv1api-keys) | Создать API ключ |
| GET | [`/api/v1/api-keys/`](#get-apiv1api-keys) | Список API ключей |
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

### Схемы

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

Список нод с пагинацией, фильтрацией по тегам и поиском.

**Query Parameters:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `page` | int | 1 | Номер страницы (≥1) |
| `size` | int | 20 | Размер страницы (1–100) |
| `tags` | string \| null | null | Теги через запятую (AND-фильтр) |
| `search` | string \| null | null | Поиск по name или host (ILIKE) |

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

## Commands

Шаблоны команд с параметрами. Позволяют сохранять часто используемые команды и выполнять их на нодах с подстановкой параметров.

### GET /api/v1/commands/

Список команд с пагинацией.

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

## API Keys

Управление API ключами для аутентификации.

### POST /api/v1/api-keys/

Создание нового API ключа. Полный ключ возвращается только один раз при создании.

**Request Body:**

```json
{
  "name": "my-app-key"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string | да | Имя ключа (1–255 символов) |

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

## Health

### GET /health

Healthcheck.

**Response 200:**

```json
{ "status": "healthy" }
```

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

### CommandUpdate

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя команды |
| `description` | string \| null | нет | Описание |
| `command` | string \| null | нет | Шаблон команды |
| `parameters` | list[CommandParameter] \| null | нет | Параметры |

### CommandResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `name` | string | Имя команды |
| `description` | string \| null | Описание |
| `command` | string | Шаблон команды |
| `parameters` | list[CommandParameter] \| null | Параметры |
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

### ScriptUpdate

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя скрипта |
| `description` | string \| null | нет | Описание |
| `steps` | list[ScriptStep] | нет | Шаги скрипта |

### ScriptResponse

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Уникальный идентификатор |
| `name` | string | Имя скрипта |
| `description` | string \| null | Описание |
| `steps` | list[ScriptStep] | Шаги скрипта |
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

## Коды ошибок

| HTTP | Описание |
|------|----------|
| 201 | Создано успешно |
| 204 | Удалено успешно |
| 401 | Не авторизован / невалидный API ключ |
| 404 | Ресурс не найден (Node, Command, Script, API Key, Container) |
| 422 | Ошибка валидации запроса / TemplateRenderError / DockerValidationError |
| 502 | Ошибка Docker-операции на удалённой ноде (DockerError) |
| 503 | Ошибка подключения к ноде (ConnectionFailedError, DockerDaemonError) |
