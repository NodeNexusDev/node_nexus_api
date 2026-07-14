# API Specification

Версия API: **v1**
Base URL: `/api/v1`

---

## Содержание

### Ресурсы

| Ресурс | Описание |
|--------|----------|
| [Nodes](#nodes) | CRUD ноды, проверка доступности, SSH-команды |
| [Audit](#audit) | Аудит-лог операций |
| [Commands](#commands) | Шаблоны команд с параметрами |
| [Scripts](#scripts) | Пайплайны команд (скрипты) |
| [Health](#health) | Healthcheck |

### Nodes

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | [`/api/v1/nodes/`](#get-apiv1nodes) | Список нод |
| GET | [`/api/v1/nodes/{node_id}`](#get-apiv1nodesnode_id) | Нода по ID |
| POST | [`/api/v1/nodes/`](#post-apiv1nodes) | Создать ноду |
| PUT | [`/api/v1/nodes/{node_id}`](#put-apiv1nodesnode_id) | Обновить ноду |
| DELETE | [`/api/v1/nodes/{node_id}`](#delete-apiv1nodesnode_id) | Удалить ноду |
| POST | [`/api/v1/nodes/{node_id}/check`](#post-apiv1nodesnode_idcheck) | Проверить SSH |
| POST | [`/api/v1/nodes/{node_id}/execute`](#post-apiv1nodesnode_idexecute) | Выполнить команду |

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

### Ошибки

| HTTP | Описание |
|------|----------|
| [404](#коды-ошибок) | Ресурс не найден |
| [422](#коды-ошибок) | Ошибка валидации / TemplateRenderError |
| [503](#коды-ошибок) | Ошибка подключения к ноде |

---

## Nodes

### GET /api/v1/nodes/

Список нод с пагинацией.

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
      "name": "web-server-01",
      "host": "192.168.1.100",
      "port": 22,
      "connection_type": "ssh",
      "status": "active",
      "username": "admin",
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
  "ssh_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n..."
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
  "status": "inactive"
}
```

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `name` | string \| null | нет | Имя ноды |
| `host` | string \| null | нет | IP или hostname |
| `port` | int \| null | нет | SSH-порт |
| `connection_type` | string \| null | нет | Тип подключения |
| `status` | string \| null | нет | Статус: `active`, `inactive`, `error` |
| `username` | string \| null | нет | Имя пользователя |
| `password` | string \| null | нет | Пароль |
| `ssh_key` | string \| null | нет | Приватный SSH-ключ |

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

### POST /api/v1/nodes/{node_id}/check

Проверка SSH-доступности ноды. Устанавливает статус `active` или `error`.

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
| `status` | string | Статус: `active`, `inactive`, `error` |
| `username` | string \| null | Имя пользователя |
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

---

## Коды ошибок

| HTTP | Описание |
|------|----------|
| 201 | Создано успешно |
| 204 | Удалено успешно |
| 404 | Ресурс не найден (Node, Command, Script) |
| 422 | Ошибка валидации запроса / TemplateRenderError |
| 503 | Ошибка подключения к ноде (ConnectionFailedError) |
