# Bulk Operations — Ревью и план улучшений

**Дата:** 2026-08-20
**Статус:** Plan

---

## Содержание

1. [Ревью: Update Node PUT](#1-update-node-put)
2. [Ревью: Текущие bulk операции](#2-ревью-текущие-bulk-операции)
3. [Несоответствия в единообразии](#3-несоответствия-в-единообразии)
4. [Где не хватает bulk](#4-где-не-хватает-bulk)
5. [План исправлений](#5-план-исправлений)
6. [Решения по tradeoff'ам](#6-решения-по-tradeoffам)

---

## 1. Update Node PUT

### Эндпоинт
`PUT /api/v1/nodes/{node_id}` — partial update

### Логика
- `model_dump(exclude_unset=True)` — передаются только явно заданные поля
- **Не передаём поле** → не меняется
- **Передаём `null`** → переписывает в `None` (для nullable полей)
- **Передаём `null` для NOT NULL** → `IntegrityError` на уровне БД (нет валидации на API)

### Nullable по полям

| Поле | NOT NULL | Передача `null` |
|------|----------|-----------------|
| `name` | YES | IntegrityError |
| `host` | YES | IntegrityError |
| `port` | YES | IntegrityError |
| `connection_type` | YES | IntegrityError |
| `status` | YES | IntegrityError |
| `username` | nullable | Очищает значение |
| `password` | nullable | Очищает значение |
| `ssh_key` | nullable | Очищает значение |
| `passphrase` | nullable | Очищает значение |
| `docker_host` | nullable | Очищает значение |
| `tags` | nullable | Очищает значение |

### OpenAPI
Все поля `anyOf: [{type: ...}, {type: "null"}]` — корректно. Нет `required` массива — все optional.

---

## 2. Ревью: Текущие bulk операции

### 2.1 SSH bulk команды (`NodeBulkCommandService`)

**Файл:** `app/application/services/node_bulk_command_service.py`

**Плюсы:**
- Параллельное выполнение через `asyncio.gather`
- Graceful error handling — каждая нода возвращает результат
- Аудит для каждой ноды
- `batch_id` для группировки истории
- `bound_output` для ограничения размера stdout/stderr

**Проблемы:**
- Нет `Semaphore` — `asyncio.gather` без лимита (risking hundreds of SSH sessions)
- `_save_history` — последовательная запись в цикле (bottleneck при большом числе нод)

### 2.2 Bulk CRUD (`NodeBulkOperationService` + `SqlAlchemyNodeBulkOperator`)

**Файлы:**
- `app/application/services/node_bulk_operation_service.py`
- `app/adapters/persistence/node_bulk_operator.py`

**Проблемы:**
- **N+1 запросы** — `bulk_add_tags`, `bulk_remove_tags`, `bulk_delete` делают `get_by_id` + `update` в цикле
- **`bulk_check`** — `asyncio.gather` прямо в endpoint, `import asyncio` внутри функции, `BulkNodeCheckDTO` не используется
- **Нет аудита** — `NodeBulkOperationService` не имеет `AuditEventSink`
- **`bulk_check` врёт** — `affected = succeeded`, но `node_ids = все переданные`

### 2.3 Docker bulk (`DockerBulkService`)

**Файл:** `app/application/services/docker/bulk_service.py`

**Плюсы:**
- Preserve result order через индексы
- Дедупликация нод по тегам
- Валидация `container_id`

**Проблемы:**
- `_resolve_node_ids` тихо глотает `Exception: tag_nodes = []`
- `timeout or 10/30` — falsy check вместо `if timeout is not None`
- **Не использует DTO** — принимает 6 kwargs вместо `BulkDockerRequestDTO`
- **Нет `AuditEventSink`** — нет записи в audit log
- **Нет `response_model`** в decorator — OpenAPI не показывает response schema
- **`node_ids: list[str]`** — валидация UUID на runtime вместо 422

---

## 3. Несоответствия в единообразии

### 3.1 Naming
- Функции: `bulk_delete_nodes`, `bulk_check_nodes` — но `bulk_execute_command`, `bulk_add_tags` — без suffix
- DTO суффиксы: `BulkCommandRequestDTO` (Request), `BulkNodeDeleteDTO` (bare), `BulkNodeTagOperationDTO` (Operation)
- Field: Docker — `node_tags`, Node — `tags`

### 3.2 Response
- Три разные структуры: `BulkCommandResult` (total/succeeded/failed + per-node), `BulkNodeOperationResult` (только affected + node_ids), `BulkDockerResponse` (total/succeeded/failed + per-node)
- `node_id` тип: UUID в node bulk, str в docker bulk

### 3.3 Error handling
- `return_exceptions=True` только в `bulk_check`, остальные — try/except в worker
- Per-node logging только в `NodeBulkCommandService`
- `DockerBulkService` не логирует per-node ошибки

### 3.4 Target resolution
- **Node bulk**: intersection (AND) через `resolve_targets()`
- **Docker bulk**: union (OR) через `_resolve_node_ids()`
- Одинаковый запрос → разный результат

### 3.5 Audit
- `NodeBulkCommandService` — имеет `AuditEventSink` + structlog
- `NodeBulkOperationService` — нет `AuditEventSink`
- `DockerBulkService` — нет `AuditEventSink`
- `GET /bulk/history` — единственный endpoint без `audit.info()`

### 3.6 DI/Scope
- `BulkCommandHistoryService` — APP scope, остальные — REQUEST scope
- `SqlAlchemyNodeBulkOperator` — APP scope + sessionmaker (другой паттерн сессий)

### 3.7 Validation
- Docker `node_ids: list[str]` vs Node `list[uuid.UUID]`
- `BulkDockerRequest.node_ids` default `[]` vs Node `None` или required
- `BulkNodeCheckRequest` нет tag support (в отличие от `BulkCommandRequest`)
- `BulkDockerRequest.command` валидация в endpoint вместо `model_validator`

### 3.8 DTO pattern
- `BulkDockerRequestDTO` определён но не используется — `DockerBulkService` принимает kwargs

### 3.9 OpenAPI
- Docker bulk endpoints — нет `response_model` в decorator

### 3.10 Мёртвый код
- `BulkNodeCheckDTO` — определён, не импортируется

---

## 4. Где не хватает bulk

| Операция | Одиночный endpoint | Приоритет |
|----------|-------------------|-----------|
| Метрики нод | `GET /nodes/{id}/metrics` | HIGH |
| Execute command template | `POST /commands/{id}/execute` | HIGH |
| Create node | `POST /nodes/` | HIGH |
| Update node | `PUT /nodes/{id}` | HIGH |
| Docker remove container | `DELETE /nodes/{id}/docker/containers/{cid}` | HIGH |
| Docker pull image | `POST /nodes/{id}/docker/images/pull` | HIGH |
| Validate credentials | `POST /nodes/validate-credentials` | MEDIUM |
| Retry command | `POST /nodes/{id}/commands/{eid}/retry` | MEDIUM |
| Cancel/Retry script | `POST /scripts/executions/{eid}/cancel`, `/retry` | MEDIUM |
| Docker remove/build image | `DELETE/POST /nodes/{id}/docker/images/...` | MEDIUM |

---

## 5. План исправлений

### Фаза 1: Fixes (без breaking changes)

| # | Задача | Файлы | Сложность |
|---|--------|-------|-----------|
| 1.1 | **Semaphore для SSH** — `max_concurrency=50` в `__init__`, `async with sem` в `_execute_on_single_node` | `node_bulk_command_service.py` | Низкая |
| 1.2 | **Batch DELETE** — `DELETE FROM nodes WHERE id = ANY(:ids)` вместо цикла | `node_bulk_operator.py` | Средняя |
| 1.3 | **Batch UPDATE tags** — `UPDATE nodes SET tags = ... WHERE id = ANY(:ids)` | `node_bulk_operator.py` | Средняя |
| 1.4 | **Exception logging** — `except Exception` → `audit.warning(...)` | `bulk_service.py:65` | Низкая |
| 1.5 | **Timeout fix** — `timeout or 10` → `if timeout is not None else 10` | `bulk_service.py:108,148` | Низкая |
| 1.6 | **`_save_history` parallel** — `asyncio.gather` вместо цикла | `node_bulk_command_service.py:179` | Низкая |
| 1.7 | **Удалить `BulkNodeCheckDTO`** | `dto/bulk_node_operation.py:20-22` | Низкая |

**Референции (Context7):**
- SQLAlchemy ORM bulk delete: `delete(Model).where(Model.id.in_(ids))` → `session.execute(stmt)`
- SQLAlchemy ORM bulk update: `update(Model).where(Model.id.in_(ids)).values(...)` → `session.execute(stmt)`
- asyncio.Semaphore — стандартная библиотека Python

---

### Фаза 2: Единообразие

| # | Задача | Файлы | Сложность |
|---|--------|-------|-----------|
| 2.1 | **`response_model`** для docker bulk — добавить `BulkDockerResponse` | `docker_bulk.py:20,42,65,88` | Низкая |
| 2.2 | **Docker `node_ids: list[str]` → `list[uuid.UUID]`** | `docker.py:229`, `bulk_service.py:30,58,91,144`, тесты | Низкая |
| 2.3 | **`DockerBulkService` → DTO** — принимать `BulkDockerRequestDTO` | `bulk_service.py`, `docker_bulk.py` | Средняя |
| 2.4 | **Audit для `NodeBulkOperationService`** — инжектить `AuditEventSink` | `node_bulk_operation_service.py`, `providers.py` | Низкая |
| 2.5 | **Audit для `DockerBulkService`** — инжектить `AuditEventSink` | `bulk_service.py`, `providers.py` | Низкая |
| 2.6 | **Audit для `GET /bulk/history`** — добавить `audit.info()` | `nodes.py:279` | Низкая |
| 2.7 | **`bulk_check` → service layer** — вынести в `NodeBulkOperationService` + порт, добавить tag support | `nodes.py`, `node_bulk_operation_service.py`, `node_bulk_operator.py`, `ports/node_bulk_operator.py` | Средняя |
| 2.8 | **Расширить `BulkNodeOperationResult`** — `total/succeeded/failed/errors` | `dto/bulk_node_operation.py`, `schemas/node.py` | Средняя |
| 2.9 | **DTO суффиксы** — единообразно `Bulk*DTO` | `dto/command_execution.py`, `dto/bulk_node_operation.py`, `dto/docker.py` | Низкая |
| 2.10 | **`node_tags` → `tags`** в docker schemas | `schemas/docker.py`, `dto/docker.py` | Низкая |
| 2.11 | **`BulkCommandHistoryService` → REQUEST scope** | `providers.py:789-795` | Низкая |
| 2.12 | **Документировать intersection vs union** — комментарии | `_target_resolver.py`, `bulk_service.py` | Низкая |

**Референции (Context7):**
- Dishka scope: `@provide(scope=Scope.REQUEST)` — per-request lifecycle
- FastAPI response_model — автоматически генерирует OpenAPI schema

---

### Фаза 3: Новые bulk операции

| # | Задача | Приоритет | Сложность |
|---|--------|-----------|-----------|
| 3.1 | **Bulk Metrics** — `POST /nodes/bulk/metrics` | HIGH | Средняя | ✅ |
| 3.2 | **Bulk Execute Command Template** — `POST /commands/{id}/bulk-execute` | HIGH | Средняя | ✅ |
| 3.3 | **Bulk Update Node** — `PUT /nodes/bulk/update` | HIGH | Средняя | ✅ |
| 3.4 | **Docker bulk remove** — `POST /docker/bulk/remove` | HIGH | Низкая | ✅ |
| 3.5 | **Docker bulk pull** — `POST /docker/bulk/pull` | HIGH | Низкая | ✅ |
| 3.6 | **Bulk Validate Credentials** — `POST /nodes/bulk/validate-credentials` | MEDIUM | Средняя |
| 3.7 | **Bulk Retry/Cancel Command** — `POST /nodes/bulk/retry` | MEDIUM | Средняя |
| 3.8 | **Bulk Cancel/Retry Script** — `POST /scripts/bulk/cancel`, `/retry` | MEDIUM | Средняя |
| 3.9 | **Docker bulk remove/build image** — `POST /docker/bulk/images/remove`, `/build` | MEDIUM | Низкая |

---

## 6. Решения по tradeoff'ам

| Вопрос | Решение | Обоснование |
|--------|---------|-------------|
| `BulkNodeOperationResult` — per-node detail | **Расширить** — добавить `total/succeeded/failed/errors` | Обратная совместимость (добавление полей), полезность для клиентов |
| Target resolution | **Оставить разные** — intersection для node bulk, union для docker bulk | Разная семантика: AND для точных операций, OR для масштабирования docker |
| Docker `node_ids` тип | **`list[uuid.UUID]`** — валидация на уровне схемы | Bug fix: 422 вместо 500 при невалидном UUID |

---

## Порядок исполнения

```
Фаза 1 (7 задач) ──────────────────────────►
  1.1 Semaphore → 1.2-1.3 Batch → 1.4-1.7 small fixes

Фаза 2 (12 задач) ─────────────────────────►
  2.1-2.2 response_model + UUID → 2.3 DTO → 2.4-2.6 Audit →
  2.7 bulk_check → 2.8 Result расширение → 2.9-2.12 Naming

Фаза 3 (9 задач) ──────────────────────────►
  3.1-3.5 HIGH → 3.6-3.9 MEDIUM
```

---

Версия плана: 1.1
Дата: 2026-08-20

## 7. Текущий статус

### Завершено
- **Фаза 1 (7 задач)** — 455f647
  - ✅ Semaphore для SSH + batch SQL DELETE/UPDATE
  - ✅ Exception logging, timeout fix, parallel `_save_history`
  - ✅ Удалён `BulkNodeCheckDTO` (dead code)
- **Фаза 2 (12 задач)** — 6ebbed0
  - ✅ `response_model` для docker bulk, UUID node_ids
  - ✅ Audit для NodeBulkOperationService, DockerBulkService, GET /bulk/history
  - ✅ `bulk_check` вынесен в сервисный слой
  - ✅ `BulkNodeOperationResult` расширен
  - ✅ DTO naming, `node_tags→tags`, REQUEST scope
- **Фаза 3 HIGH (5 задач)** — текущая сессия
  - ✅ 3.1 Bulk Metrics — `POST /nodes/bulk/metrics`
  - ✅ 3.2 Bulk Execute Command Template — `POST /commands/{id}/bulk-execute`
  - ✅ 3.3 Bulk Update Node — `PUT /nodes/bulk/update`
  - ✅ 3.4 Docker bulk remove — `POST /docker/bulk/remove`
  - ✅ 3.5 Docker bulk pull — `POST /docker/bulk/pull`

### Осталось (MEDIUM приоритет)
- ❌ 3.6 Bulk Validate Credentials — `POST /nodes/bulk/validate-credentials`
- ❌ 3.7 Bulk Retry/Cancel Command — `POST /nodes/bulk/retry`
- ❌ 3.8 Bulk Cancel/Retry Script — `POST /scripts/bulk/cancel`, `/retry`
- ❌ 3.9 Docker bulk remove/build image — `POST /docker/bulk/images/remove`, `/build`

### Архитектурные решения (текущая сессия)
- `DockerBulkService.bulk_pull_image()` возвращает `BulkDockerPullResultsDTO` (DTO), а не schema — для соблюдения границы application ↔ schemas
- `bulk_container_action()` теперь поддерживает `remove` action (`docker rm -f`)
- `BulkDockerPullResultDTO` добавлен в `app/application/dto/docker.py`
