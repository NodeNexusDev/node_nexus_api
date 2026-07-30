---
title: Глоссарий
status: stable
translation_key: reference.glossary
source_revision: "2026-07-30"
---

# Глоссарий

**Advisory lock**
: Механизм PostgreSQL (`pg_advisory_lock`) для кооперативного владения
  ресурсом без блокировки чтения. В Node Nexus гарантирует, что только одна
  реплика выполняет scheduled jobs.
  См. [runtime lifecycle](../architecture/runtime-lifecycle.md).

**Application core**
: Слой `app/application`: DTO, ports (Protocols), use cases и policies.
  Не содержит импортов фреймворков и инфраструктуры.
  См. [правила зависимостей](../architecture/dependency-rules.md).

**APScheduler**
: Внутрипроцессный планировщик Python, эфемерная runtime-проекция
  персистентных расписаний. Jobs перестраиваются из PostgreSQL при запуске.
  См. [ADR-003](../architecture/decisions/ADR-003-scheduler-lifecycle.md).

**Audit outbox**
: Паттерн гарантированной доставки: события аудита пишутся в таблицу
  `audit_outbox` в той же транзакции, что и бизнес-изменение, а затем
  доставляются асинхронно фоновым worker.
  См. [ADR-011](../architecture/decisions/ADR-011-audit-outbox-boundary.md).

**Composition root**
: Единственное место (`app/di/providers.py`), где application ports
  связываются с concrete adapters. Каждая привязка использует явный
  `provides=Port`.
  См. [правила зависимостей](../architecture/dependency-rules.md).

**Conventional Commits**
: Формат коммитов (`type(scope): description`) для обозначения характера
  изменений. Типы: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
  См. [workflow разработки](../development/workflow.md).

**Cursor pagination**
: Пагинация по ключу с параметрами `cursor` и `limit`. Эффективнее offset
  для больших наборов данных, так как не сканирует пропущенные строки.
  Cursor — base64-encoded кортеж `(created_at, id)`.

**DAO (Data Access Object)**
: Внутренний session-bound помощник в `app/adapters/persistence/dao/`.
  Выполняет `flush()`, но не владеет commit/rollback — это зона
  ответственности provider или gateway.

**Dishka**
: Фреймворк внедрения зависимостей. Предоставляет scope APP и REQUEST.
  Composition root (`app/di/providers.py`) — единственное место связывания
  ports и adapters.

**DTO (Data Transfer Object)**
: Неизменяемый `@dataclass(frozen=True, slots=True)`, пересекающий границу
  application. Application DTO не зависят от фреймворков; Pydantic-схемы —
  transport DTO. ORM-модели никогда не являются DTO.

**Offset pagination**
: Постраничная пагинация с параметрами `page` и `size`. Возвращает `total`,
  `page`, `size` и `items`. Проще cursor, но медленнее на глубоких страницах.

**Outbox (audit)**
: См. **Audit outbox** выше.

**Port**
: Класс `Protocol` в `app/application/ports/`, определяющий
  узконаправленный контракт (например, `NodeManagementReader`). Ports —
  единственные зависимости application services. Adapters реализуют ports.

**Ports & Adapters**
: Архитектурный стиль (также известен как Hexagonal Architecture). Transport
  и инфраструктура — adapters; бизнес-логика зависит только от ports.
  См. [ADR-001](../architecture/decisions/ADR-001-layer-boundaries.md).

**Reconciliation**
: Процесс сверки расписаний PostgreSQL с runtime-проекцией APScheduler и
  восстановления расхождений: добавление отсутствующих, замена изменённых,
  удаление лишних. Запускается при старте и периодически.

**Session (база данных)**
: SQLAlchemy `AsyncSession`. В Node Nexus сессии бывают request-scoped (одна
  на HTTP-запрос, provider владеет commit) или открываются по требованию
  APP gateways через `async_sessionmaker` для коротких операций.

**Unit of Work (UoW)**
: Паттерн группировки операций нескольких repository в одну транзакцию.
  Node Nexus намеренно избегает универсального UoW; многоаггрегатная
  атомарность достигается через специализированные ports, такие как
  `ConfigurationImporter`.
  См. [ADR-002](../architecture/decisions/ADR-002-session-and-transaction-scope.md).
