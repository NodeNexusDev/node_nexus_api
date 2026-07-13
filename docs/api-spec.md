# API Specification

Версия API: **v1**
Base URL: `/api/v1`

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

### CommandRequest

| Поле | Тип | Описание |
|------|-----|----------|
| `command` | string | Команда для выполнения |

### CommandResult

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
| 404 | Нода не найдена |
| 422 | Ошибка валидации запроса |
| 503 | Ошибка подключения к ноде |
