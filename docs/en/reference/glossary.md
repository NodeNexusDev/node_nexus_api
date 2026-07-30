---
title: Glossary
status: stable
translation_key: reference.glossary
source_revision: "2026-07-30"
---

# Glossary

**Advisory lock**
: A PostgreSQL mechanism (`pg_advisory_lock`) that allows cooperative
  resource ownership without blocking reads. In Node Nexus, it ensures only
  one replica executes scheduled jobs at a time.
  See [runtime lifecycle](../architecture/runtime-lifecycle.md).

**Application core**
: The `app/application` layer: DTOs, ports (Protocols), use cases, and
  policies. It contains no framework or infrastructure imports.
  See [dependency rules](../architecture/dependency-rules.md).

**APScheduler**
: An in-process Python job scheduler used as an ephemeral runtime projection
  of persistent schedules. Jobs are rebuilt from PostgreSQL on startup.
  See [ADR-003](../architecture/decisions/ADR-003-scheduler-lifecycle.md).

**Audit outbox**
: A durable delivery pattern: audit events are written to an `audit_outbox`
  table in the same transaction as the business change, then delivered
  asynchronously by a background worker.
  See [ADR-011](../architecture/decisions/ADR-011-audit-outbox-boundary.md).

**Composition root**
: The single place (`app/di/providers.py`) where application ports are bound
  to concrete adapters. Every binding uses explicit `provides=Port`.
  See [dependency rules](../architecture/dependency-rules.md).

**Conventional Commits**
: A commit message format (`type(scope): description`) used to communicate
  the nature of a change. Types include `feat`, `fix`, `docs`, `refactor`,
  `test`, `chore`.
  See [development workflow](../development/workflow.md).

**Cursor pagination**
: Keyset-based pagination using `cursor` and `limit` parameters. More
  efficient than offset for large datasets because it does not scan skipped
  rows. Cursors are base64-encoded `(created_at, id)` tuples.

**DAO (Data Access Object)**
: An internal session-bound helper inside `app/adapters/persistence/dao/`.
  DAOs perform `flush()` but never own commit/rollback — that belongs to
  the provider or gateway boundary.

**Dishka**
: The dependency injection framework. Provides APP and REQUEST scopes.
  The composition root (`app/di/providers.py`) is the only place that binds
  ports to adapters.

**DTO (Data Transfer Object)**
: An immutable `@dataclass(frozen=True, slots=True)` that crosses the
  application boundary. Application DTOs are framework-free; Pydantic
  schemas are transport DTOs. ORM models are never DTOs.

**Offset pagination**
: Page-based pagination using `page` and `size` parameters. Returns `total`,
  `page`, `size`, and `items`. Simpler than cursor pagination but slower for
  deep pages.

**Outbox (audit)**
: See **Audit outbox** above.

**Port**
: A `Protocol` class in `app/application/ports/` that defines a focused
  contract (e.g., `NodeManagementReader`). Ports are the only dependencies
  of application services. Adapters implement ports.

**Ports & Adapters**
: The architectural style (also known as Hexagonal Architecture). Transport
  and infrastructure are adapters; application logic depends only on ports.
  See [ADR-001](../architecture/decisions/ADR-001-layer-boundaries.md).

**Reconciliation**
: The process that compares PostgreSQL schedules with APScheduler runtime
  jobs and repairs differences: adds missing, replaces changed, removes
  orphans. Runs on startup and periodically.

**Session (database)**
: A SQLAlchemy `AsyncSession`. In Node Nexus, sessions are either
  request-scoped (one per HTTP request, provider owns commit) or opened
  on-demand by APP gateways via `async_sessionmaker` for short operations.

**Unit of Work (UoW)**
: A pattern that groups multiple repository operations into one transaction.
  Node Nexus deliberately avoids a universal UoW; multi-aggregate atomicity
  uses dedicated ports like `ConfigurationImporter`.
  See [ADR-002](../architecture/decisions/ADR-002-session-and-transaction-scope.md).
