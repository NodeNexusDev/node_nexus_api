# Node Nexus API — UI Completeness Plan

Статус: **Stage F Completed**
Проект: **Node Nexus API**
Дата: **2026-08-16**
Владелец: **Backend**

---

## 1. Цель

Закрыть функциональные пробелы API для полноценного UI: история операций,
поиск, консистентность тегов, агрегированная статистика, безопасный импорт,
массовые операции, жизненный цикл выполнения и удобные UX-фичи.

---

## 2. Проблемы

| # | Проблема | Impact на UI |
|---|----------|--------------|
| 1 | Нет истории одиночных команд и bulk-команд | UI не показывает "последние операции" |
| 2 | Нет поиска по name/description для Commands и Scripts | Автокомплит, фильтрация не работают |
| 3 | Scripts/Commands не имеют глобального списка тегов | UI не может показать все доступные теги |
| 4 | Scripts execute принимает только `node_ids`, не теги | Нет масштабирования как у Commands bulk |
| 5 | Нет dashboard/overview endpoint | Нет обзорной страницы с агрегированной статистикой |
| 6 | Audit: нет фильтра по дате и user | Удобный просмотр логов невозможен |
| 7 | Config import: нет dry-run режима | Опасно импортировать без предпросмотра |
| 8 | Нет webhook'ов на события | Нет мониторинга и алертов |
| 9 | Нет массовых операций над нодами | Удаление/тегирование по одной — медленно |
| 10 | Нет retry/cancel для выполнений | UI не может повторить или остановить операцию |
| 11 | Нет истории статусов нод | Нет графиков доступности |
| 12 | Нет истории запусков по расписанию | Не видно, как отрабатывает cron |
| 13 | Нет глобального поиска | Поиск разбит по разделам |
| 14 | Нет статистики executions | Не видно success rate и длительность |
| 15 | Нет live event stream | UI обновляется только polling'ом |

---

## 3. Архитектурные принципы реализации

План приведён в соответствие с архитектурой Ports & Adapters и современными
практиками FastAPI/SQLAlchemy/Dishka (по данным актуальной документации):

- **Application слой** зависит только от DTO и узких `Protocol` портов.
- **Persistence adapters** располагаются в `app/adapters/persistence/`, ORM-модели — в `app/models/`.
- **Application DTO** — immutable `dataclass(frozen=True, slots=True)` в `app/application/dto/`.
- **Response schemas** — Pydantic-модели в `app/schemas/`; router выполняет только mapping DTO ↔ schema.
- **Output bounding**: stdout/stderr команд ограничиваются политикой `bound_output()` перед сохранением.
- **Query objects**: фильтры и пагинация передаются через DTO (`*ListQueryDTO`, `*HistoryQueryDTO`).
  Для сложных query params в FastAPI рекомендуется использовать Pydantic-модель
  через `Annotated[FilterParams, Query()]` — это даёт валидацию, OpenAPI-документацию
  и переиспользуемость.
- **Event-driven webhooks**: сервисы публикуют события через `EventPublisher` port, concrete delivery скрыт в runtime adapter.
- **SQLAlchemy async**: короткие сессии через `async_sessionmaker`, `scalars()` для выборки скаляров,
  `DateTime(timezone=True)` для timestamp'ов, PostgreSQL `func.unnest()` для тегов.
- **Dishka scopes**: APP-scoped gateways хранят `sessionmaker`, REQUEST-scoped — `AsyncSession`;
  binding port → adapter выполняется явно через `provides=Port`.

Запрещено:
- создавать `app/application/repositories/` или возвращать `app/repositories/`;
- передавать `AsyncSession`/ORM/DAO в application service;
- хранить request-scoped `AsyncSession` в APP-scoped gateway;
- удерживать DB transaction во время SSH/Docker I/O;
- логировать полные команды, credentials или неограниченный stdout/stderr.

---

## 4. Приоритеты и этапы

| # | Задача | Приоритет | Этап | Размер |
|---|--------|-----------|------|--------|
| 1 | История команд (single + bulk) | 🟢 High | A | M |
| 2 | Search для Commands/Scripts | 🟢 High | A | S |
| 3 | Tags для Scripts/Commands (global list) | 🟢 High | A | S |
| 4 | Bulk execute scripts по тегам | 🟢 High | B | S |
| 5 | Dashboard endpoint | 🟡 Medium | B | M |
| 6 | Audit: фильтр по дате/user | 🟡 Medium | B | S |
| 7 | Dry-run config import | 🟡 Medium | C | S |
| 8 | Webhooks на события | 🟡 Medium | C | L |
| 9 | Массовые операции над нодами | 🟢 High | D | M |
| 10 | Retry / Cancel execution | 🟢 High | D | M |
| 11 | Node status history | 🟡 Medium | D | S |
| 12 | Scheduled execution history | 🟡 Medium | D | S |
| 13 | Execution statistics | 🟡 Medium | E | S |
| 14 | Global search | 🟢 High | E | M |
| 15 | Live event stream (SSE) | 🟡 Medium | E | M |
| 16 | Global tag management, clone, favorites | 🔴 Low | F | S |

Этапы упорядочены так, чтобы каждый следующий опирался на предыдущий:
**A (Foundation) → B (Observability) → C (Config automation) → D (Operations lifecycle) → E (UX & search) → F (Power features).**

---

## 5. Этап A — Foundation: история команд, поиск, теги

### A.1 История одиночных команд

**Endpoint:** `GET /api/v1/nodes/{node_id}/commands/history`

**Query params:**
- `page: int = 1`
- `size: int = 20`

**Response:** paginated `CommandHistoryResponse` с `command_fingerprint`, bounded `stdout`/`stderr`, `truncated`, `stdout_bytes`, `stderr_bytes`.

**Implementation:**
1. Model `app/models/command_execution.py` (`CommandExecutionModel`) с индексами по `node_id`, `created_at`.
2. DTO `app/application/dto/command_history.py`: `CommandHistoryDTO`, `CommandHistoryQueryDTO`, `CommandHistoryPageDTO`.
3. Ports `app/application/ports/command_history.py`: `CommandHistoryWriter`, `CommandHistoryReader`.
4. Adapter `app/adapters/persistence/command_history.py`: `SqlAlchemyCommandHistoryGateway`.
5. Расширить `NodeCommandService`: сохранять `CommandHistoryDTO` через `CommandHistoryWriter` с `bound_output()`.
6. Schema `CommandHistoryResponse` в `app/schemas/node.py`.
7. Endpoint в `app/api/v1/nodes.py`.
8. DI в `app/di/providers.py`.
9. Alembic migration.
10. Tests: unit service, adapter mapping, E2E, architecture tests, container graph.

---

### A.2 История bulk-команд

**Endpoint:** `GET /api/v1/nodes/bulk/history`

**Response:** paginated `BulkCommandHistoryResponse`.

**Implementation:**
1. Добавить `batch_id: UUID | None` в `CommandExecutionModel` (миграция `b7a8c9d0e1f2`).
2. DTO: `CommandHistoryCreateDTO.batch_id`, `CommandHistoryDTO.batch_id`, `BulkCommandHistoryQueryDTO`.
3. Ports: `CommandHistoryReader.list_by_batch()`.
4. Gateway: `list_by_batch()`, `count_by_batch()` в `SqlAlchemyCommandHistoryGateway`.
5. `NodeBulkCommandService`: генерирует `batch_id`, сохраняет результат через `CommandHistoryWriter`.
6. `BulkCommandHistoryService.get_batch_history()`.
7. Schema `BulkCommandHistoryItem` (с `batch_id`), `BulkCommandHistoryResponse`.
8. Endpoint `GET /api/v1/nodes/bulk/history` в `app/api/v1/nodes.py`.
9. DI, tests.

---

### A.3 Search для Commands

**Изменение:** добавить `search` query param в `GET /api/v1/commands/`.

**Implementation:**
1. Расширить `CommandListQueryDTO.search: str | None`.
2. В `SqlAlchemyCommandGateway` и `CommandRepository` добавить ILIKE фильтр по `name` и `description`.
3. API: `search: str | None = Query(None)`.
4. Tests: service, adapter, E2E.

---

### A.4 Search для Scripts

Аналогично A.3, но для `ScriptListQueryDTO` и `SqlAlchemyScriptGateway`.

---

### A.5 Global tags для Scripts

**Endpoint:** `GET /api/v1/scripts/tags`

**Implementation:**
1. Добавить `ScriptReader.list_tags()` в порт.
2. Реализовать через `select(func.unnest(ScriptModel.tags)).distinct()`.
3. `ScriptManagementService.get_all_tags()`.
4. Endpoint, tests.

---

### A.6 Global tags для Commands

**Endpoint:** `GET /api/v1/commands/tags`

Аналогично A.5.

---

## 6. Этап B — Observability: Dashboard, Audit, Bulk scripts

### B.1 Bulk execute scripts по тегам

**Проблема:** `POST /api/v1/scripts/{script_id}/execute` принимает только `node_ids`.

**Решение:** добавить `node_tags`, аналогично `BulkCommandRequest`.

```python
class ScriptExecuteRequest(BaseModel):
    node_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    node_tags: list[str] | None = Field(default=None, min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_targets(self) -> "ScriptExecuteRequest":
        if not self.node_ids and not self.node_tags:
            raise ValueError("At least one of node_ids or node_tags must be provided")
        return self
```

**Implementation:**
1. `ScriptExecutionRequestDTO`: `node_ids` и `node_tags` опциональные.
2. В `ScriptExecutionService.execute_script` резолвить теги через `NodeConnectionReader.get_connections_by_tags()`.
3. Обновить `app/schemas/script.py`, `app/api/v1/scripts.py`, tests.

---

### B.2 Dashboard / Overview endpoint

**Endpoint:** `GET /api/v1/dashboard`

**Response:** `DashboardResponse` с `nodes`, `docker`, `scripts`, `commands`, `recent_activity`.

**Implementation:**
1. DTO `app/application/dto/dashboard.py`.
2. Port `app/application/ports/dashboard.py`: `DashboardReader`.
3. Adapter `app/adapters/persistence/dashboard.py`: `SqlAlchemyDashboardGateway`.
4. Service `app/application/services/dashboard_service.py`.
5. API `app/api/v1/dashboard.py`, schema `app/schemas/dashboard.py`.
6. Регистрация в `app/main.py`, DI, tests.
7. Docker stats: на первом этапе возвращать нули с TODO/ADR; реальная реализация через кеширование или background job позже.

---

### B.3 Audit: фильтр по дате и user

**Изменение:** расширить `GET /api/v1/audit/`.

**Query params:**
- `from_date: datetime | None`
- `to_date: datetime | None`
- `user: str | None`

**Implementation:**
1. Расширить `AuditLogQueryDTO` полями `user`, `from_date`, `to_date`.
2. В `SqlAlchemyAuditLogGateway.list_logs` добавить фильтры.
3. Обновить `AuditLogService`, `app/api/v1/audit.py`, tests.

---

## 7. Этап C — Config automation: Dry-run import, validation

### C.1 Dry-run config import

**Изменение:** добавить `dry_run` параметр в `POST /api/v1/config/import`.

**Implementation:**
1. Расширить `ConfigImportResultDTO`: `dry_run`, `would_create`, `duplicates`.
2. Расширить `ConfigurationImporter` методом `preview_import()`.
3. Реализовать `SqlAlchemyConfigGateway.preview_import()` без записи.
4. `ConfigService.import_config`: if `dto.dry_run` → `preview_import`.
5. Обновить `ConfigImport`, `ImportResult` schemas.
6. API, tests.

### C.2 Validate credentials before save

**Endpoint:** `POST /api/v1/nodes/validate-credentials`

**Purpose:** проверить SSH connectivity с предоставленными credentials без сохранения ноды.

**Implementation:**
1. DTO `NodeCredentialsDTO`.
2. Port `NodeCredentialValidator`.
3. Adapter использует `RemoteConnectorFactory`.
4. Service `NodeValidationService`.
5. API, schema, tests.

---

## 8. Этап D — Operations lifecycle: Bulk ops, Retry/Cancel, Status history

### D.1 Массовые операции над нодами

**Endpoints:**
```http
POST /api/v1/nodes/bulk/delete
POST /api/v1/nodes/bulk/tags/add
POST /api/v1/nodes/bulk/tags/remove
POST /api/v1/nodes/bulk/check
```

**Implementation:**
1. DTO `BulkNodeOperationDTO`, `BulkNodeTagOperationDTO`.
2. Port `NodeBulkOperator`.
3. Adapter `SqlAlchemyNodeBulkOperator`.
4. Service `NodeBulkOperationService`.
5. API, schemas, tests.

**Note:** bulk delete — опасная операция, требует `require_write_scope` и audit.

---

### D.2 Retry / Cancel execution

**Endpoints:**
```http
POST /api/v1/nodes/{node_id}/commands/{execution_id}/retry
POST /api/v1/scripts/executions/{execution_id}/retry
POST /api/v1/scripts/executions/{execution_id}/cancel
```

**Implementation:**
1. Для retry: по `execution_id` загрузить историю, повторить ту же команду/скрипт с теми же параметрами.
2. Для cancel: требуется хранить `pid` или `task_id` выполнения. Ввести `Job` entity или расширить `ScriptExecutionModel`/`CommandExecutionModel` полем `cancel_token`.
3. Port `ExecutionLifecycleManager`.
4. Adapter + service + API + tests.

---

### D.3 Node status history

**Endpoint:** `GET /api/v1/nodes/{node_id}/status-history?from_date=...&to_date=...`

**Implementation:**
1. Model `app/models/node_status_history.py`.
2. DTO, port, adapter.
3. `NodeCommandService.check_connectivity` и `NodeManagementService.update_node` публикуют изменения статуса.
4. API, schema, migration, tests.

---

### D.4 Scheduled execution history

**Endpoint:** `GET /api/v1/scripts/{script_id}/schedule/history`

**Implementation:**
1. Расширить `ScriptExecutionModel`: `trigger: Literal["manual", "scheduled", "retry"]`, `schedule_id`, `triggered_by`.
2. `ScheduledScriptExecutor` сохраняет `trigger="scheduled"`.
3. Endpoint фильтрует по `script_id` и `trigger="scheduled"`.
4. Tests.

---

## 9. Этап E — UX & Analytics: Statistics, Global search, Event stream, Export

### E.1 Execution statistics

**Endpoints:**
```http
GET /api/v1/commands/{command_id}/stats
GET /api/v1/scripts/{script_id}/stats
GET /api/v1/nodes/{node_id}/stats
```

**Response:**
```json
{
  "total_executions": 150,
  "successful": 142,
  "failed": 8,
  "success_rate": 0.947,
  "avg_duration_ms": 1250,
  "last_executed_at": "2026-08-11T10:30:00Z"
}
```

**Implementation:**
1. DTO `ExecutionStatsDTO`.
2. Port `ExecutionStatsReader`.
3. Adapter агрегирует из `command_executions`, `script_execution`.
4. Service, API, schema, tests.

---

### E.2 Global search

**Endpoint:** `GET /api/v1/search?q=nginx&limit=20`

**Response:**
```json
{
  "nodes": [...],
  "commands": [...],
  "scripts": [...],
  "tags": ["nginx", "web"]
}
```

**Implementation:**
1. DTO `GlobalSearchQueryDTO`, `GlobalSearchResultDTO`.
2. Port `GlobalSearchReader`.
3. Adapter делает несколько parallel SELECT с ILIKE.
4. Service, API, schema, tests.

---

### E.3 Metrics for charts

**Endpoint:** `GET /api/v1/dashboard/metrics?from_date=...&to_date=...&group_by=day`

**Response:** time-series data для executions/failures/duration.

**Implementation:**
1. DTO `DashboardMetricsDTO`.
2. Расширить `DashboardReader`.
3. SQL GROUP BY date_trunc.
4. API, schema, tests.

---

### E.4 Live event stream (SSE)

**Endpoint:** `GET /api/v1/events/stream`

**Events:** `node.status_changed`, `execution.completed`, `job.progress`, `script.scheduled`.

**Implementation:**
1. Использовать существующий `EventPublisher` port из этапа C (Webhooks).
2. Добавить `SseEventPublisher` adapter в `app/adapters/runtime/sse_event_publisher.py`.
3. Endpoint использует FastAPI `StreamingResponse`.
4. DI, tests.

---

### E.5 Export

**Endpoints:**
```http
GET /api/v1/audit/export?format=csv&from_date=...&to_date=...
GET /api/v1/nodes/{node_id}/commands/history/export?format=csv
GET /api/v1/nodes/export?format=json
```

**Implementation:**
1. Port `AuditExporter`, `CommandHistoryExporter`.
2. Adapters формируют CSV/JSON из DTO.
3. StreamingResponse для больших выгрузок.
4. API, tests.

---

## 10. Этап F — Power features: Tag management, Clone, Favorites, Notes

### F.1 Global tag management

**Endpoints:**
```http
PATCH /api/v1/tags/{tag_name}      # rename
DELETE /api/v1/tags/{tag_name}     # delete tag from all entities
```

**Implementation:**
1. Port `TagManager`.
2. Adapter обновляет `tags` массивы в nodes/commands/scripts.
3. Service, API, tests.

---

### F.2 Clone command/script

**Endpoints:**
```http
POST /api/v1/commands/{command_id}/clone
POST /api/v1/scripts/{script_id}/clone
```

**Implementation:**
1. DTO `CloneCommandDTO`/`CloneScriptDTO` с опциональным новым именем.
2. В сервисе загрузить существующий entity, создать копию с суффиксом `-copy`.
3. API, schema, tests.

---

### F.3 Favorites / recent

**Endpoints:**
```http
GET    /api/v1/me/favorites
POST   /api/v1/me/favorites
DELETE /api/v1/me/favorites/{favorite_id}
```

**Implementation:**
1. Model `favorite_items` с `entity_type`, `entity_id`, `user` (API key hash/name).
2. Port + adapter + service + API.
3. Tests.

---

### F.4 Notes on nodes and executions

**Endpoints:**
```http
GET/POST /api/v1/nodes/{node_id}/notes
GET/POST /api/v1/nodes/{node_id}/commands/{execution_id}/notes
```

**Implementation:**
1. Model `notes`.
2. Port + adapter + service + API.
3. Tests.

---

## 11. Порядок выполнения

```
Этап A (Foundation)
├── A.1 Command history
├── A.2 Bulk command history
├── A.3 Search commands
├── A.4 Search scripts
├── A.5 Script tags
└── A.6 Command tags

Этап B (Observability)
├── B.1 Bulk execute scripts by tags
├── B.2 Dashboard
└── B.3 Audit filters

Этап C (Config automation)
├── C.1 Dry-run import
└── C.2 Validate credentials

Этап D (Operations lifecycle)
├── D.1 Bulk node operations
├── D.2 Retry / Cancel execution
├── D.3 Node status history
└── D.4 Scheduled execution history

Этап E (UX & Analytics)
├── E.1 Execution statistics
├── E.2 Global search
├── E.3 Dashboard metrics
├── E.4 Live event stream (SSE)
└── E.5 Export

Этап F (Power features)
├── F.1 Global tag management
├── F.2 Clone command/script
├── F.3 Favorites
└── F.4 Notes
```

**Логика последовательности:**
- A закладывает базу: история, поиск, теги.
- B добавляет масштабирование и обзорность.
- C делает импорт безопасным.
- D добавляет операционные возможности: массовые действия, retry, lifecycle.
- E улучшает UX: поиск, статистика, live updates, выгрузка.
- F — «nice to have» для power users.

Каждый этап — отдельная feature-ветка. Этапы A и B можно запускать параллельно,
так как они почти не пересекаются по файлам. Этапы C–F зависят от предыдущих.

---

## 12. Миграции

| Этап | Таблица | Тип |
|------|---------|-----|
| A.1 | `command_executions` | CREATE TABLE |
| A.2 | `command_executions` | ADD COLUMN `batch_id` |
| B.1 | — | schema change only |
| B.2 | — | new endpoint, no table |
| B.3 | — | query change only |
| C.1 | — | schema change only |
| C.2 | — | new endpoint, no table |
| D.1 | — | new endpoints, no table |
| D.2 | `script_executions` / `command_executions` | ADD COLUMN `cancel_token` |
| D.3 | `node_status_history` | CREATE TABLE |
| D.4 | `script_executions` | ADD COLUMN `trigger`, `schedule_id` |
| E.1 | — | query change only |
| E.2 | — | query change only |
| E.3 | — | query change only |
| E.4 | — | new endpoint, no table |
| E.5 | — | new endpoint, no table |
| F.1 | — | query change only |
| F.2 | — | new endpoints, no table |
| F.3 | `favorite_items` | CREATE TABLE |
| F.4 | `notes` | CREATE TABLE |

---

## 13. Версионирование

| Этап | Commits | Bump |
|------|---------|------|
| A | `feat(api): add command history, search, tags` | MINOR |
| B | `feat(api): add bulk scripts by tags, dashboard, audit filters` | MINOR |
| C | `feat(api): add dry-run import, credentials validation` | MINOR |
| D | `feat(api): add bulk node operations, retry/cancel, status history, scheduled history` | MINOR |
| E | `feat(api): add execution stats, global search, metrics, sse, export` | MINOR |
| F | `feat(api): add tag management, clone, favorites, notes` | MINOR |

**Общий bump:** текущая → +6 minor (или +1 minor при merge в один release).

---

## 14. Definition of Done

### Общие критерии для всех этапов
- [ ] Application service зависит только от DTO и портов (нет ORM/DAO/session).
- [ ] Persistence adapter возвращает application DTO, не ORM/schema.
- [ ] Port binding `provides=Port` добавлен в `app/di/providers.py`.
- [ ] Container graph test разрешает новые зависимости.
- [ ] Architecture guard обновлён при новой границе.
- [ ] Ruff / ty / pytest зелёные, coverage ≥95%.
- [ ] Alembic migration создана и проверена на PostgreSQL.
- [ ] OpenAPI snapshot обновлён осознанно.

### Этап A
- [x] `GET /api/v1/nodes/{id}/commands/history` работает и покрыт тестами.
- [x] `GET /api/v1/nodes/bulk/history` работает и покрыт тестами.
- [x] stdout/stderr в истории ограничены `bound_output()`.
- [x] `GET /api/v1/commands/?search=...` фильтрует по name/description.
- [x] `GET /api/v1/scripts/?search=...` фильтрует по name/description.
- [x] `GET /api/v1/scripts/tags` и `GET /api/v1/commands/tags` возвращают уникальные теги.
- [x] Миграции применены, Alembic clean.

### Этап B
- [x] `POST /api/v1/scripts/{id}/execute` поддерживает `node_tags`.
- [x] `GET /api/v1/dashboard` возвращает агрегированную статистику.
- [x] Dashboard реализован через один `DashboardReader` port.
- [x] `GET /api/v1/audit/?from_date=...&to_date=...&user=...` фильтрует.
- [x] E2E тесты проходят.

### Этап C
- [x] `POST /api/v1/config/import` с `dry_run=true` возвращает preview без записи.
- [x] `POST /api/v1/nodes/validate-credentials` проверяет SSH без сохранения.

### Этап D
- [x] Bulk delete/add/remove tags/check работают.
- [x] Retry / Cancel execution работают.
- [x] `GET /api/v1/nodes/{id}/status-history` возвращает историю.
- [x] `GET /api/v1/scripts/{id}/schedule/history` возвращает scheduled runs.

### Этап E
- [x] Execution statistics endpoints работают.
- [x] Global search endpoint работает.
- [x] Dashboard metrics endpoint работает.
- [x] SSE stream доставляет события.
- [x] Export endpoints работают.

### Этап F
- [x] Global tag rename/delete работает.
- [x] Clone command/script работает.
- [x] Favorites CRUD работает.
- [x] Notes CRUD работает.

---

## 15. Риски

| Риск | Вероятность | Impact | Mitigation |
|------|-------------|--------|------------|
| Таблица `command_executions` растёт бесконечно | High | Medium | Cron job для очистки; bound_output |
| Утечка sensitive-данных в `command_executions.stdout` | Medium | High | bound_output + command_fingerprint |
| Webhook delivery блокирует основной поток | Medium | High | Async delivery; timeout 10s; логирование |
| Dashboard endpoint медленный | Medium | Medium | Кеширование; background job для Docker stats |
| Bulk delete нод — необратимая операция | Medium | High | Требовать `require_write_scope`; confirmation param |
| Cancel execution требует управления SSH процессами | Medium | High | Хранить PID/контракт с connector; fallback — ignore |
| SSE stream при большом числе клиентов грузит сервер | Low | Medium | Limit connections; heartbeat; отключать при бездействии |
| Нарушение архитектурных границ | Medium | High | Code review; architecture tests |

---

## 16. Приложения

### A. Supported webhook events

```python
WebhookEvent = Literal[
    "node.created",
    "node.updated",
    "node.deleted",
    "node.status_changed",
    "command.executed",
    "command.failed",
    "bulk_command.executed",
    "script.executed",
    "script.failed",
    "docker.container.stopped",
    "docker.container.died",
]
```

### B. Webhook payload format

```json
{
  "event": "node.status_changed",
  "timestamp": "2026-08-11T10:30:00Z",
  "payload": {
    "node_id": "uuid",
    "name": "web-01",
    "old_status": "active",
    "new_status": "unreachable"
  }
}
```

### C. Pydantic query model для фильтров (рекомендация)

```python
from typing import Annotated
from fastapi import Query
from pydantic import BaseModel, Field


class AuditFilterParams(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None
    user: str | None = None
    action: str | None = None
    node_id: uuid.UUID | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


@router.get("/")
async def get_audit_logs(
    filters: Annotated[AuditFilterParams, Query()],
    ...
):
    ...
```

---

Версия документа: 4.0
Дата последнего обновления: 2026-08-16
